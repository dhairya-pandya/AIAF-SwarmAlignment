"""OpenAI-compatible client for NVIDIA / OpenRouter / Ollama with rate limits and a sqlite cache.

Model specs are "provider:model", e.g. "openrouter:meta-llama/llama-3.1-8b-instruct:free".
The "mock" provider is offline and deterministic; it exists for tests and dry runs."""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Provider:
    name: str
    base_url: str | None
    key_env: str | None
    rpm: float


PROVIDERS = {
    "nvidia": Provider("nvidia", "https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY", 40),
    "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", 20),
    "ollama": Provider("ollama", "http://localhost:11434/v1", None, 600),
    "mock": Provider("mock", None, None, 1e9),
}

# Per-model request extras (e.g. {"chat_template_kwargs": {"enable_thinking": False}}). Empty: models think by
# default; the pilot switched it off for throughput (DEVIATIONS D17).
MODEL_EXTRA: dict[str, dict] = {
    "nvidia/nemotron-3.5-lightning-30b-a3b": {"chat_template_kwargs": {"enable_thinking": False}},
}


def parse_spec(spec: str) -> tuple[Provider, str]:
    prov, _, model = spec.partition(":")
    if prov not in PROVIDERS:
        raise ValueError(f"unknown provider {prov!r} in {spec!r}")
    rpm = os.environ.get(f"HIVEGUARD_RPM_{prov.upper()}")
    p = PROVIDERS[prov]
    if rpm:
        p = Provider(p.name, p.base_url, p.key_env, float(rpm))
    return p, model


class CacheMiss(RuntimeError):
    pass


class Cache:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS c (k TEXT PRIMARY KEY, v TEXT, meta TEXT)")
        self.lock = threading.Lock()

    def get(self, k: str) -> str | None:
        with self.lock:
            row = self.db.execute("SELECT v FROM c WHERE k=?", (k,)).fetchone()
        return row[0] if row else None

    def put(self, k: str, v: str, meta: dict) -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO c VALUES (?,?,?)", (k, v, json.dumps(meta)))
            self.db.commit()


def cache_key(provider: str, model: str, messages: list[dict], seed: int, temperature: float,
              max_tokens: int, extra: dict | None = None) -> str:
    blob = json.dumps([provider, model, messages, seed, temperature, max_tokens, extra or {}], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def _mock_reply(messages: list[dict], seed: int) -> str:
    """Deterministic stand-in: prefers a declared target, else the best option by its own facts."""
    text = "\n".join(m["content"] for m in messages)
    opts = re.findall(r"^- ([A-H]) \(", text, flags=re.M) or ["A"]
    rng = random.Random(seed)
    m = re.search(r"Your hidden target is option ([A-H])", text)
    if m:
        choice, conf = m.group(1), 0.95
    else:
        weights = {a: int(w) for a, w in re.findall(r"(\w+) x(\d)", text)}
        score = {o: 0.0 for o in opts}
        for o, a, v in re.findall(r"\b([A-H])\.(\w+) = (\d+)", text):
            if o in score:
                score[o] += weights.get(a, 1) * (int(v) - 5)
        best = max(score.values())
        choice = rng.choice([o for o, s in score.items() if s == best])
        conf = round(0.5 + 0.4 * rng.random(), 2)
    return json.dumps({"choice": choice, "confidence": conf, "claims": [], "endorse": [], "stop": [],
                       "message": f"I pick {choice}."})


class LLMClient:
    def __init__(self, cache_path: str | Path = ".cache/llm.sqlite", replay_only: bool = False,
                 max_tokens: int = 1200):
        self.cache = Cache(cache_path)
        self.replay_only = replay_only
        self.max_tokens = max_tokens
        self._clients: dict[str, object] = {}
        self._next_slot: dict[str, float] = {}
        self._lock = threading.Lock()
        self.stats = {"calls": 0, "hits": 0, "errors": 0, "prompt_tokens": 0, "completion_tokens": 0}

    def _client(self, p: Provider):
        if p.name not in self._clients:
            from openai import OpenAI
            key = os.environ.get(p.key_env) if p.key_env else "ollama"
            if p.key_env and not key:
                raise RuntimeError(f"set {p.key_env} to use provider {p.name}")
            self._clients[p.name] = OpenAI(base_url=p.base_url, api_key=key, max_retries=0, timeout=120)
        return self._clients[p.name]

    def _wait_slot(self, p: Provider) -> None:
        gap = 60.0 / p.rpm
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot.get(p.name, 0.0))
            self._next_slot[p.name] = slot + gap
        if slot > now:
            time.sleep(slot - now)

    def complete(self, spec: str, messages: list[dict], seed: int, temperature: float) -> str:
        p, model = parse_spec(spec)
        k = cache_key(p.name, model, messages, seed, temperature, self.max_tokens, MODEL_EXTRA.get(model))
        hit = self.cache.get(k)
        if hit is not None:
            self.stats["hits"] += 1
            return hit
        if self.replay_only:
            raise CacheMiss(k)
        if p.name == "mock":
            text = _mock_reply(messages, seed)
        else:
            text = self._call(p, model, messages, seed, temperature)
        self.cache.put(k, text, {"provider": p.name, "model": model, "seed": seed, "t": time.time()})
        return text

    def _call(self, p: Provider, model: str, messages, seed, temperature) -> str:
        client = self._client(p)
        delay = 2.0
        for attempt in range(14):
            self._wait_slot(p)
            try:
                r = client.chat.completions.create(model=model, messages=messages,
                                                   temperature=temperature, seed=seed,
                                                   max_tokens=self.max_tokens,
                                                   extra_body=MODEL_EXTRA.get(model))
                self.stats["calls"] += 1
                if r.usage:
                    self.stats["prompt_tokens"] += r.usage.prompt_tokens or 0
                    self.stats["completion_tokens"] += r.usage.completion_tokens or 0
                return r.choices[0].message.content or ""
            except Exception as e:  # rate limits, 5xx, timeouts: back off and retry
                self.stats["errors"] += 1
                status = getattr(e, "status_code", None)
                if status is not None and status < 500 and status not in (408, 409, 429):
                    raise
                time.sleep(delay + random.random())
                delay = min(delay * 2, 60)
        raise RuntimeError(f"{p.name}:{model} failed after retries")

"""Structured agent output (DESIGN §5.2), validated with pydantic."""
from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field, ValidationError, field_validator


class Claim(BaseModel):
    option: str
    attribute: str
    value: int = Field(ge=0, le=10)
    source: str = "own"

    @field_validator("option")
    @classmethod
    def _opt(cls, v: str) -> str:
        return v.strip().upper()[:1]

    @field_validator("source")
    @classmethod
    def _src(cls, v) -> str:
        return str(v).strip().lower()


class Output(BaseModel):
    choice: str
    confidence: float = Field(ge=0.0, le=1.0)
    claims: list[Claim] = Field(default_factory=list)
    endorse: list[str] = Field(default_factory=list)
    stop: list[str] = Field(default_factory=list)
    message: str = ""

    @field_validator("choice")
    @classmethod
    def _choice(cls, v: str) -> str:
        return v.strip().upper()[:1]

    @field_validator("message")
    @classmethod
    def _msg(cls, v: str) -> str:
        words = v.split()
        return " ".join(words[:60])

    @field_validator("claims", mode="before")
    @classmethod
    def _claims(cls, v):
        # a malformed claim (e.g. a weighted total like value=73) is dropped, not the whole reply
        keep = []
        for c in v or []:
            try:
                keep.append(Claim.model_validate(c))
            except ValidationError:
                pass
        return keep

    @field_validator("endorse", "stop", mode="before")
    @classmethod
    def _ids(cls, v):
        return [str(x) for x in (v or [])]


MAX_CLAIMS, MAX_MARKS = 8, 3

SCHEMA_TEXT = """{
  "choice": "<option id, e.g. A>",
  "confidence": <number between 0 and 1>,
  "claims": [at most 8 of {"option": "<id>", "attribute": "<name>", "value": <0-10>, "source": "own" or "<agent id you got it from>"}],
  "endorse": [at most 3 "<claim id>"],
  "stop": [at most 3 "<claim id>"],
  "message": "<at most 60 words>"
}"""


def extract_json(text: str) -> str:
    """Pull the first top-level JSON object out of a model reply (handles code fences, prose)."""
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise ValueError("unbalanced JSON")


def parse_output(text: str, valid_options: set[str]) -> Output:
    """Raises ValueError on anything that is not a valid Output with a legal choice."""
    try:
        out = Output.model_validate(json.loads(extract_json(text)))
    except (ValidationError, json.JSONDecodeError) as e:
        raise ValueError(str(e)[:300]) from e
    if out.choice not in valid_options:
        raise ValueError(f"choice {out.choice!r} not in {sorted(valid_options)}")
    out.claims = [c for c in out.claims if c.option in valid_options][:MAX_CLAIMS]
    out.endorse, out.stop = out.endorse[:MAX_MARKS], out.stop[:MAX_MARKS]
    return out

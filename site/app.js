/* Swarm Immunity results page. Plain JS, no dependencies. Every number comes from data/*.json.
   The hero swarm is an illustration (stepped, not data); sprites come from sprites.js (design/sprites.py). */
"use strict";
(function () {
  const SVGNS = "http://www.w3.org/2000/svg";
  const SOURCES = ["ABM", "LLM", "pilot"];
  const SOURCE_NAMES = { ABM: "Agent-based model (ABM)", LLM: "LLM swarms", pilot: "LLM pilot" };
  const DEFAULTS = { module: "none", attack: "A2", topology: "full", N: 12, placement: "random" };
  const SEARCHERS = { random: "Random", hub: "Hub (betweenness)", ga: "Genetic algorithm", bpso: "Binary PSO",
    map_elites: "MAP-Elites" };
  const FIG_CAPTIONS = {
    fig1_leaderboard_abm: "Leaderboard, agent-based model", fig1_leaderboard_llm: "Leaderboard, LLM swarms",
    fig2_pareto: "Safety vs usefulness per strategy and defence", fig3_con_vs_f: "Contamination vs attacker fraction",
    fig4_topology_heatmap: "Contamination by topology", fig5_modules_components: "Defence effects and component clustering",
    fig6_redteam: "Red-team searchers: best attack found vs budget", fig6_mapelites: "MAP-Elites archive of attacks",
    fig7_abm_vs_llm: "ABM vs LLM contamination (proxy fidelity)" };
  const VERDICT_TEXT = { "not run": "not run yet" };

  const D = { manifest: null, results: null, labels: null, cells: null, replays: [] };
  const S = { src: null, keys: {}, f: null, modSrc: "ABM", modScope: "overall", hypSrc: "all" };

  // ------------------------------------------------------------ helpers
  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    setAttrs(n, attrs);
    append(n, kids);
    return n;
  }
  function sv(tag, attrs, ...kids) {
    const n = document.createElementNS(SVGNS, tag);
    setAttrs(n, attrs);
    append(n, kids);
    return n;
  }
  function setAttrs(n, attrs) {
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "text") n.textContent = v;
      else if (k === "class") n.setAttribute("class", v);
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : String(v));
    }
  }
  function append(n, kids) {
    for (const k of kids.flat()) {
      if (k == null || k === false) continue;
      n.appendChild(typeof k === "string" || typeof k === "number" ? document.createTextNode(String(k)) : k);
    }
  }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); return n; }
  const $ = (q) => document.querySelector(q);
  const isNum = (x) => typeof x === "number" && isFinite(x);
  const fmt = (x, d = 2) => (isNum(x) ? Number(x).toFixed(d) : "—");
  const pTxt = (name, p) => (isNum(p) ? (p < 0.001 ? `${name} < 0.001` : `${name} = ${p.toFixed(3)}`) : `${name} —`);
  const ci = (m, lo, hi, d = 2) => (isNum(m) ? `${fmt(m, d)} [${fmt(lo, d)}, ${fmt(hi, d)}]` : "—");
  const frac = (f) => {
    if (!isNum(f)) return "—";
    for (const den of [12, 6, 50, 200]) {
      const k = Math.round(f * den);
      if (k > 0 && Math.abs(k / den - f) < 1e-4 && den <= 12) return `${k}/${den} (${f.toFixed(3)})`;
    }
    return f.toFixed(3);
  };
  const sName = (id) => (D.labels && D.labels.strategies[id] ? D.labels.strategies[id].name : id);
  const mName = (id) => (D.labels && D.labels.modules[id] ? D.labels.modules[id].name : id);
  const aName = (id) => (D.labels && D.labels.attacks[id] ? D.labels.attacks[id].name : id);
  const tName = (id) => (D.labels && D.labels.topologies[id]) || id;
  // Option colours carry meaning: the correct option is sky (accuracy), the attackers' target vermilion
  // (contamination); any other option gets a neutral categorical hue. Abstain is an unlit tile.
  const optColor = (c) => {
    if (c < 0) return "var(--abstain)";
    const d = RP.data;
    if (d && c === d.correct) return "var(--acc)";
    if (d && c === d.target) return "var(--con)";
    return `var(--o${c % 8})`;
  };
  const optText = (c) => (c < 0 ? "var(--si-ink)" : "var(--si-surface)");

  // ------------------------------------------------------------ pixel sprites (design/sprites.py)
  const PX = { lime: "#a6dd62", sky: "#6fb7ff", amber: "#ffc95c", vermilion: "#e8361c", red1: "#33100c",
    red2: "#5c130e", red3: "#8f150f", red4: "#c4170f", bone: "#d6b48c", paper: "#f2e9da", off: "#1c1916",
    ground: "#0b0908" };
  const PALETTES = {
    red: { b: PX.red4, d: PX.red2, h: PX.bone, a: PX.vermilion, e: PX.paper },
    attack: { b: PX.vermilion, d: PX.red3, h: PX.paper, a: PX.vermilion, e: PX.ground },
    lime: { b: PX.lime, d: "#3a5220", h: PX.paper, a: PX.amber, e: PX.ground },
    sky: { b: PX.sky, d: "#213d5c", h: PX.paper, a: PX.amber, e: PX.ground },
    bone: { b: PX.bone, d: PX.red3, h: PX.paper, a: PX.vermilion, e: PX.ground } };
  const STRATEGY_SPRITE = { S0a: "agent", S0b: "agent", S1: "agent", S2: "agent", S3: "particle", S4: "ant", S5: "bee",
    S6: "firefly", S7: "wolf", S8: "bird", S9: "bee", S10: "ant", S11: "bat" };
  const SPR = () => window.SI_SPRITES || {};
  function spriteSVG(name, pal, cls, title) {
    const g = SPR()[name];
    if (!g) return null;
    const p = PALETTES[pal] || PALETTES.red, w = g[0].length, h = g.length, gap = 0.16;
    const svg = sv("svg", { class: cls || "sprite-ic", viewBox: `0 0 ${w} ${h}`, "shape-rendering": "crispEdges",
      role: title ? "img" : null, "aria-label": title || null, "aria-hidden": title ? null : "true",
      preserveAspectRatio: "xMidYMid meet" });
    g.forEach((row, y) => [...row].forEach((ch, x) => {
      if (ch !== "." && p[ch]) svg.appendChild(sv("rect", { x: x + gap / 2, y: y + gap / 2, width: 1 - gap, height: 1 - gap, fill: p[ch] }));
    }));
    return svg;
  }
  const stratIcon = (s) => spriteSVG(STRATEGY_SPRITE[s] || "agent", "red", "sprite-ic");

  function renderCast() {
    const box = $("#cast");
    if (!box) return;
    clear(box);
    const cast = [["ant", "red", "Ants", "S4 trails · S10 roles"], ["bee", "red", "Honeybees", "S5 foraging · S9 nest-site"],
      ["wolf", "red", "Wolves", "S7 pack hierarchy"], ["bird", "red", "Birds", "S8 boids"],
      ["firefly", "red", "Fireflies", "S6 attraction"], ["bat", "red", "Vampire bats", "S11 trust · exploratory"],
      ["particle", "red", "Abstract", "S1 vote · S2 debate · S3 PSO"], ["compromised", "attack", "Compromised", "pushes the target"]];
    for (const [sp, pal, name, sub] of cast) {
      box.appendChild(el("li", {}, spriteSVG(sp, pal, "", `${name} sprite`), el("div", {}, el("b", { text: name }), el("small", { text: sub }))));
    }
  }

  // ------------------------------------------------------------ hero: a stepped pixel-mosaic swarm (illustration)
  function heroSwarm() {
    const cv = document.getElementById("swarm");
    if (!cv || !cv.getContext) return;
    const ctx = cv.getContext("2d");
    const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const order = ["ant", "bee", "wolf", "bird", "firefly", "bat"];
    let W = 0, H = 0, cell = 14, cols = 0, rows = 0, agents = [], tex = [], sprite = null, ep = 0;
    let phase = "spread", step = 0, scan = -1, timer = null, visible = true;
    const rnd = (() => { let x = 2463534242; return () => ((x ^= x << 13, x ^= x >>> 17, x ^= x << 5) >>> 0) / 4294967296; })();

    function layoutSprite() {
      const name = order[ep % order.length], g = SPR()[name];
      if (!g) { sprite = null; return; }
      const wide = W >= 900;
      const sc = wide ? 2 : 1;                       // each sprite pixel = sc x sc mosaic cells
      const sw = g[0].length * sc, sh = g.length * sc;
      const c0 = Math.max(0, Math.min(cols - sw - 1, Math.round(cols * (wide ? 0.76 : 0.5) - sw / 2)));
      const r0 = Math.max(1, Math.round(rows * (wide ? 0.27 : 0.5) - sh / 2));
      sprite = { name, g, sc, c0, r0 };
    }
    function spriteAt(c, r) {
      if (!sprite) return null;
      const x = Math.floor((c - sprite.c0) / sprite.sc), y = Math.floor((r - sprite.r0) / sprite.sc);
      if (y < 0 || y >= sprite.g.length || x < 0 || x >= sprite.g[0].length) return null;
      const ch = sprite.g[y][x];
      return ch === "." ? null : PALETTES.red[ch] || null;
    }
    function reset() {
      step = 0; phase = "spread"; scan = -1;
      layoutSprite();
      const n = Math.max(24, Math.min(150, Math.round(cols * rows * 0.05)));
      agents = [];
      for (let i = 0; i < n; i++) {
        const k = i < Math.max(2, Math.round(n * 0.06)) ? "bad" : rnd() < 0.28 ? "informed" : "honest";
        agents.push({ c: Math.floor(rnd() * cols), r: Math.floor(rnd() * rows), k, base: k, flash: 0 });
      }
    }
    function resize() {
      const rect = cv.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      W = Math.max(1, rect.width); H = Math.max(1, rect.height);
      cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      cell = W < 600 ? 12 : 14;
      cols = Math.ceil(W / cell); rows = Math.ceil(H / cell);
      tex = Array.from({ length: cols * rows }, () => rnd());
      reset();
    }
    function tick() {
      step++;
      for (const a of agents) {                      // stepped random walk, one cell at a time
        if (a.flash) a.flash--;
        if (rnd() < 0.45) {
          a.c = Math.max(0, Math.min(cols - 1, a.c + Math.floor(rnd() * 3) - 1));
          a.r = Math.max(0, Math.min(rows - 1, a.r + Math.floor(rnd() * 3) - 1));
        }
      }
      if (phase === "spread") {                      // compromised and misled tiles turn their neighbours
        const src = agents.filter((a) => a.k === "bad" || a.k === "misled");
        for (const a of agents) {
          if (a.k !== "honest" && a.k !== "informed") continue;
          const near = src.some((b) => Math.abs(b.c - a.c) <= 2 && Math.abs(b.r - a.r) <= 2);
          if (near && rnd() < (a.k === "informed" ? 0.025 : 0.14)) { a.k = "misled"; a.flash = 2; }
        }
        const misled = agents.filter((a) => a.k === "misled").length / agents.length;
        if (misled > 0.5 || step > 90) { phase = "immune"; scan = 0; }
      } else if (phase === "immune") {               // a defence sweep restores misled tiles, stepping column by column
        scan += 2;
        for (const a of agents) if (a.k === "misled" && a.c <= scan) { a.k = a.base; a.flash = 3; }
        if (scan > cols + 6) { ep++; reset(); }
      }
    }
    const COL = { honest: PX.lime, informed: PX.sky, misled: PX.red4, bad: PX.vermilion };
    function draw() {
      ctx.fillStyle = PX.ground;
      ctx.fillRect(0, 0, W, H);
      const g = 2, t = cell - g;
      for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
        const sp = spriteAt(c, r);
        if (sp) { ctx.fillStyle = sp; ctx.fillRect(c * cell + 1, r * cell + 1, t, t); continue; }
        const v = tex[r * cols + c];
        if (v < 0.42) continue;
        ctx.fillStyle = v > 0.985 ? "#2b1411" : PX.off;
        ctx.fillRect(c * cell + 1, r * cell + 1, t, t);
      }
      if (phase === "immune" && scan >= 0) {
        ctx.fillStyle = PX.paper;
        ctx.fillRect(Math.min(scan, cols) * cell, 0, 3, H);
      }
      for (const a of agents) {
        const x = a.c * cell + 1, y = a.r * cell + 1;
        ctx.fillStyle = a.flash ? PX.paper : COL[a.k];
        ctx.fillRect(x, y, t, t);
        if (a.k === "bad") { ctx.fillStyle = PX.red1; ctx.fillRect(x + t / 2 - 2, y + t / 2 - 2, 4, 4); }
      }
    }
    function loop() {
      timer = null;
      if (!visible || document.hidden) return;
      tick(); draw();
      timer = setTimeout(() => requestAnimationFrame(loop), 200);
    }
    function start() { if (!timer && !reduce) timer = setTimeout(() => requestAnimationFrame(loop), 200); }
    resize();
    if (reduce) { for (let i = 0; i < 22; i++) tick(); draw(); }
    else { draw(); start(); }
    if (window.ResizeObserver) {
      let last = W;
      new ResizeObserver(() => { const w = cv.getBoundingClientRect().width; if (Math.abs(w - last) > 4) { last = w; resize(); draw(); } }).observe(cv);
    }
    if (window.IntersectionObserver) {
      new IntersectionObserver((es) => { visible = es[0].isIntersecting; if (visible) start(); }).observe(cv);
    }
    document.addEventListener("visibilitychange", () => { if (!document.hidden) start(); });
  }
  const sortStrat = (a, b) => {
    const k = (s) => { const m = /^S(\d+)([a-z]?)$/.exec(s); return m ? +m[1] * 10 + (m[2] ? m[2].charCodeAt(0) - 96 : 0) : 999; };
    return k(a) - k(b);
  };
  const empty = (text) => el("div", { class: "empty", text });

  async function getJSON(path, optional) {
    try {
      const r = await fetch(path, { cache: "no-cache" });
      if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
      return await r.json();
    } catch (e) {
      if (optional) return null;
      throw e;
    }
  }

  // ------------------------------------------------------------ status
  function renderStatus() {
    const m = D.manifest || {}, meta = (D.results && D.results.meta) || {};
    const box = clear($("#status"));
    const cal = !!meta.calibrated;
    const inputs = meta.inputs || {};
    const llmIn = Object.keys(inputs).filter((k) => k.startsWith("llm"));
    const items = [
      `Agent-based model runs: ${isNum(meta.abm_rows) ? meta.abm_rows.toLocaleString() : "not run yet"}`,
      `LLM swarm runs: ${isNum(meta.llm_rows) ? meta.llm_rows.toLocaleString() : "not run yet"}` +
        (llmIn.length && !isNum(meta.llm_rows) ? " (input file missing)" : ""),
      `LLM pilot: ${inputs.pilot && !inputs.pilot.missing ? "included" : "not run yet"}`,
      `ABM parameters: ${meta.params ? "frozen from " + meta.params.path : "defaults (not calibrated)"}`,
    ];
    const notRun = (D.results.hypotheses || []).filter((h) => h.verdict === "not run").length;
    if (notRun) items.push(`${notRun} of ${D.results.hypotheses.length} hypothesis tests not run yet`);
    const gen = meta.generated ? ` Results generated ${meta.generated}.` : "";
    box.appendChild(el("div", { class: cal ? "banner ok" : "banner" },
      el("strong", { text: cal ? "Calibrated results" : "Exploratory, uncalibrated data. These are not final results." }),
      el("p", { text: cal
        ? `The ABM was calibrated on LLM pilot runs before these results were produced.${gen}`
        : `The agent-based model has not yet been calibrated against LLM pilot runs, so every number on this page is a development preview and may change.${gen}` }),
      el("ul", {}, items.map((t) => el("li", { text: t })))));
    if (!cal) document.querySelectorAll(".chip-slot").forEach((s) => s.appendChild(el("span", { class: "chip", text: "Exploratory" })));
  }

  // ------------------------------------------------------------ cells and filters
  const cellCache = {};
  function cellsFor(src) {
    if (cellCache[src]) return cellCache[src];
    const c = D.cells && D.cells[src];
    if (!c || !c.rows || !c.rows.length) return null;
    const cols = c.columns;
    const rows = c.rows.map((r) => Object.fromEntries(cols.map((k, i) => [k, r[i]])));
    const keyCols = cols.slice(0, cols.indexOf("n"));
    const filterKeys = keyCols.filter((k) => k !== "strategy" && k !== "f_eff");
    const values = {};
    for (const k of filterKeys) {
      values[k] = [...new Set(rows.map((r) => JSON.stringify(r[k])))].map((s) => JSON.parse(s))
        .sort((a, b) => (typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b))));
    }
    return (cellCache[src] = { rows, filterKeys, values });
  }
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  function matchRows() {
    const c = cellsFor(S.src);
    if (!c) return [];
    return c.rows.filter((r) => c.filterKeys.every((k) => same(r[k], S.keys[k])));
  }
  function setSource(src) {
    S.src = src;
    const c = cellsFor(src);
    S.keys = {};
    if (!c) return;
    for (const k of c.filterKeys) {
      const vals = c.values[k];
      const want = DEFAULTS[k];
      S.keys[k] = vals.some((v) => same(v, want)) ? want : vals[0];
    }
    S.f = null;
    pickF();
  }
  function fOptions() {
    return [...new Set(matchRows().map((r) => r.f_eff).filter((f) => f > 0))].sort((a, b) => a - b);
  }
  function pickF() {
    const fs = fOptions();
    if (S.f != null && fs.some((f) => Math.abs(f - S.f) < 1e-9)) return;
    let best = null;
    for (const f of fs) if (best == null || Math.abs(f - 0.25) < Math.abs(best - 0.25) - 1e-9) best = f;
    S.f = best;
  }
  const keyLabel = (k) => ({ module: "Defence", attack: "Attack", topology: "Topology", N: "Agents (N)", R: "Rounds",
    onset: "Onset", placement: "Placement", models: "Models" }[k] || k);
  function valueLabel(k, v) {
    if (k === "module") return v === "none" ? "none" : `${v} ${mName(v)}`;
    if (k === "attack") return `${v} ${aName(v)}`;
    if (k === "topology") return tName(v);
    if (Array.isArray(v)) return v.join(", ");
    return v == null ? "—" : String(v);
  }
  function select(label, options, current, onChange) {
    const s = el("select", { "aria-label": label });
    options.forEach((o, i) => {
      const opt = el("option", { value: String(i), text: o.label, disabled: o.disabled });
      if (same(o.value, current)) opt.selected = true;
      s.appendChild(opt);
    });
    s.addEventListener("change", () => onChange(options[+s.value].value));
    return el("label", {}, label, s);
  }
  function renderMainFilters() {
    document.querySelectorAll('[data-filters="main"]').forEach((box) => {
      clear(box);
      box.appendChild(select("Data source", SOURCES.map((s) => ({ value: s,
        label: SOURCE_NAMES[s] + (cellsFor(s) ? "" : " (not run yet)"), disabled: !cellsFor(s) })), S.src,
      (v) => { setSource(v); renderMain(); }));
      const c = cellsFor(S.src);
      if (!c) return;
      for (const k of c.filterKeys) {
        if (c.values[k].length < 2 && !["module", "attack", "topology", "N"].includes(k)) continue;
        box.appendChild(select(keyLabel(k), c.values[k].map((v) => ({ value: v, label: valueLabel(k, v) })), S.keys[k],
          (v) => { S.keys[k] = v; pickF(); renderMain(); }));
      }
      const fs = fOptions();
      box.appendChild(select("Attacker fraction f (leaderboard)",
        fs.length ? fs.map((f) => ({ value: f, label: frac(f) })) : [{ value: null, label: "—", disabled: true }], S.f,
        (v) => { S.f = v; renderMain(); }));
    });
  }
  function renderMain() {
    renderMainFilters();
    renderLeaderboard();
    renderCurves();
  }

  function tipFor(strategy) {
    const tips = (D.results.tipping || {})[S.src] || [];
    const k = S.keys;
    if ((k.module != null && k.module !== "none") || (k.attack != null && k.attack !== "A2") ||
        (k.placement != null && k.placement !== "random")) return null;
    return tips.find((t) => t.strategy === strategy && t.topology === k.topology && t.N === k.N) || null;
  }

  // ------------------------------------------------------------ leaderboard
  function barSVG(m, lo, hi, color, title) {
    const W = 100, H = 22;
    const svg = sv("svg", { class: "bar", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", role: "img",
      "aria-label": title });
    svg.appendChild(sv("title", { text: title }));
    svg.appendChild(sv("rect", { x: 0, y: 4, width: W, height: 14, fill: "var(--surface-2)" }));
    if (isNum(m)) {
      svg.appendChild(sv("rect", { x: 0, y: 6, width: Math.max(0.6, m * W), height: 10, fill: color }));
      if (isNum(lo) && isNum(hi)) {
        const ln = (x1, y1, x2, y2) => sv("line", { x1, y1, x2, y2, stroke: "var(--fg)", "stroke-width": 1.4,
          "vector-effect": "non-scaling-stroke" });
        svg.append(ln(lo * W, 11, hi * W, 11), ln(lo * W, 6, lo * W, 16), ln(hi * W, 6, hi * W, 16));
      }
    }
    return svg;
  }
  function renderLeaderboard() {
    const body = clear($("#lb-body"));
    if (!cellsFor(S.src)) { body.appendChild(empty(`${SOURCE_NAMES[S.src] || "These"} results: not run yet.`)); renderHeadline(); return; }
    const rows = matchRows();
    if (!rows.length) { body.appendChild(empty("No runs for this combination of filters (not run yet).")); renderHeadline(); return; }
    const strat = [...new Set(rows.map((r) => r.strategy))].sort(sortStrat);
    const list = strat.map((s) => {
      const atF = rows.find((r) => r.strategy === s && S.f != null && Math.abs(r.f_eff - S.f) < 1e-9);
      const at0 = rows.find((r) => r.strategy === s && r.f_eff === 0);
      return { s, atF, at0, tip: tipFor(s) };
    });
    list.sort((a, b) => {
      const x = a.atF ? a.atF.con : null, y = b.atF ? b.atF.con : null;
      if (x == null && y == null) return sortStrat(a.s, b.s);
      if (x == null) return 1; if (y == null) return -1;
      return x - y || sortStrat(a.s, b.s);
    });
    const t = el("table", { class: "lb" });
    t.appendChild(el("thead", {}, el("tr", {},
      el("th", { class: "c-rank", text: "#" }), el("th", { class: "c-name", text: "Strategy" }),
      el("th", { text: `Contamination at f = ${S.f != null ? S.f.toFixed(3) : "—"}` }),
      el("th", { text: "Accuracy at f = 0" }), el("th", { class: "c-f", text: "Tipping f*" }))));
    const tb = el("tbody");
    list.forEach((r, i) => {
      const c = r.atF, a = r.at0;
      const conT = c ? `Contamination ${ci(c.con, c.con_lo, c.con_hi)}, ${c.n} seeds` : "not run yet";
      const accT = a ? `Accuracy ${ci(a.acc, a.acc_lo, a.acc_hi)}, ${a.n} seeds` : "not run yet";
      let fs = "—", fsT = "Tipping point is only fitted for the core grid (no defence, attack A2, random placement).";
      if (r.tip) {
        if (r.tip.in_range) { fs = fmt(r.tip.f_star); fsT = `f* ${ci(r.tip.f_star, r.tip.lo, r.tip.hi)}, transition width ${fmt(r.tip.width)}`; }
        else if (r.tip.f_star == null) { fs = "none"; fsT = r.tip.note || "No contamination at any f"; }
        else { fs = `> ${fmt(r.tip.f_max)}`; fsT = `Fitted f* = ${fmt(r.tip.f_star)} lies outside the tested range (max f = ${fmt(r.tip.f_max)})`; }
      } else if (tipFor(r.s) === null && (D.results.tipping || {})[S.src] && S.keys.module === "none") {
        fsT = "Not fitted for this cell (needs at least 3 attacker fractions).";
      }
      tb.appendChild(el("tr", {},
        el("td", { class: "c-rank", text: String(i + 1) }),
        el("td", { class: "c-name" }, el("span", { class: "sname", text: sName(r.s) }), el("span", { class: "sid" }, stratIcon(r.s), r.s)),
        el("td", {}, barSVG(c && c.con, c && c.con_lo, c && c.con_hi, "var(--con)", conT),
          el("span", { class: "num", title: conT }, c ? [el("b", { text: fmt(c.con) }), " ", el("span", { class: "ci", text: `[${fmt(c.con_lo)}, ${fmt(c.con_hi)}]` })] : "not run yet")),
        el("td", {}, barSVG(a && a.acc, a && a.acc_lo, a && a.acc_hi, "var(--acc)", accT),
          el("span", { class: "num", title: accT }, a ? [el("b", { text: fmt(a.acc) }), " ", el("span", { class: "ci", text: `[${fmt(a.acc_lo)}, ${fmt(a.acc_hi)}]` })] : "not run yet")),
        el("td", { class: "c-f" }, el("span", { class: "num", title: fsT }, el("b", { text: fs })))));
    });
    t.appendChild(tb);
    body.appendChild(t);
    renderHeadline();
  }
  function renderHeadline() {
    const box = clear($("#lb-headline"));
    const lb = (D.results.leaderboard || {})[S.src];
    if (!lb || !lb.length) { box.appendChild(empty("Not run yet for this data source.")); return; }
    const fu = (x) => (x && x.f_used ? ` (f used: ${x.f_used.map((v) => fmt(v, 3)).join(", ")})` : "");
    const c = (x) => (x ? ci(x.mean, x.lo, x.hi) : "not run yet");
    const t = el("table", { class: "simple" },
      el("thead", {}, el("tr", {}, ["Strategy", "Accuracy f=0", "Contamination f=1/12", "Contamination f=3/12", "f*", "Calls/run"]
        .map((h) => el("th", { text: h })))),
      el("tbody", {}, lb.map((r) => el("tr", {},
        el("td", { text: `${r.strategy} ${sName(r.strategy)}` }), el("td", { text: c(r.acc_f0) }),
        el("td", { text: c(r["con_1/12"]) + fu(r["con_1/12"]) }), el("td", { text: c(r["con_3/12"]) + fu(r["con_3/12"]) }),
        el("td", { text: r.f_star == null ? "—" : r.f_star_in_range ? fmt(r.f_star) : `outside grid (max ${fmt(r.f_max)})` }),
        el("td", { text: r.calls == null ? "—" : fmt(r.calls, 0) })))));
    box.appendChild(el("div", { class: "tbl-wrap" }, t));
    box.appendChild(el("p", { class: "note-sm", text: "When the grid has no f exactly at 3/12, the analysis averages the two nearest fractions (listed as f used)." }));
  }

  // ------------------------------------------------------------ curves
  function renderCurves() {
    const body = clear($("#curves-body"));
    if (!cellsFor(S.src)) { body.appendChild(empty("Not run yet for this data source.")); return; }
    const rows = matchRows();
    if (!rows.length) { body.appendChild(empty("No runs for this combination of filters (not run yet).")); return; }
    const maxF = Math.max(...rows.map((r) => r.f_eff)) || 1;
    const strat = [...new Set(rows.map((r) => r.strategy))].sort(sortStrat);
    for (const s of strat) {
      const pts = rows.filter((r) => r.strategy === s).sort((a, b) => a.f_eff - b.f_eff);
      const tip = tipFor(s);
      const sub = tip ? (tip.in_range ? `f* = ${ci(tip.f_star, tip.lo, tip.hi)}` : tip.f_star == null ? "no contamination at any f" : `f* beyond tested range`) : "";
      body.appendChild(el("div", { class: "mult" },
        el("h3", {}, stratIcon(s), `${sName(s)} `, el("span", { text: s })), el("div", { class: "sub", text: sub || " " }),
        curveSVG(pts, maxF, tip && tip.in_range ? tip.f_star : null, s)));
    }
  }
  function curveSVG(pts, maxF, fstar, s) {
    const W = 260, H = 168, L = 30, R = 14, T = 10, B = 32;
    const x = (f) => L + (f / maxF) * (W - L - R), y = (v) => T + (1 - v) * (H - T - B);
    const svg = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Contamination and accuracy vs attacker fraction for ${s}` });
    for (const v of [0, 0.5, 1]) {
      svg.appendChild(sv("line", { class: "gridline", x1: L, x2: W - R, y1: y(v), y2: y(v) }));
      svg.appendChild(sv("text", { x: L - 4, y: y(v) + 3, "text-anchor": "end", "font-size": 9, text: v.toFixed(1) }));
    }
    [0, maxF / 2, maxF].forEach((f, i) => svg.appendChild(sv("text", { x: x(f), y: H - B + 12, "text-anchor": ["start", "middle", "end"][i], "font-size": 9, text: f.toFixed(2) })));
    svg.appendChild(sv("text", { x: (L + W - R) / 2, y: H - 3, "text-anchor": "middle", "font-size": 9, text: "attacker fraction f" }));
    const band = (m, lo, hi, color) => {
      const ok = pts.filter((p) => isNum(p[lo]) && isNum(p[hi]));
      if (ok.length < 2) return;
      const d = ok.map((p, i) => `${i ? "L" : "M"}${x(p.f_eff)},${y(p[hi])}`).join("") +
        ok.slice().reverse().map((p) => `L${x(p.f_eff)},${y(p[lo])}`).join("") + "Z";
      svg.appendChild(sv("path", { d, fill: color, opacity: 0.16, stroke: "none" }));
    };
    const line = (m, color, dash) => {
      const ok = pts.filter((p) => isNum(p[m]));
      if (!ok.length) return;
      svg.appendChild(sv("path", { d: ok.map((p, i) => `${i ? "L" : "M"}${x(p.f_eff)},${y(p[m])}`).join(""), fill: "none",
        stroke: color, "stroke-width": 2, "stroke-dasharray": dash || null }));
      for (const p of ok) {
        const c = sv("rect", { x: x(p.f_eff) - 2.4, y: y(p[m]) - 2.4, width: 4.8, height: 4.8, fill: color });
        c.appendChild(sv("title", { text: `${m === "con" ? "Contamination" : "Accuracy"} at f=${p.f_eff.toFixed(3)}: ${ci(p[m], p[m + "_lo"], p[m + "_hi"])} (${p.n} seeds)` }));
        svg.appendChild(c);
      }
    };
    band("acc", "acc_lo", "acc_hi", "var(--acc)");
    band("con", "con_lo", "con_hi", "var(--con)");
    line("acc", "var(--acc)", "5 3");
    line("con", "var(--con)");
    if (isNum(fstar)) {
      svg.appendChild(sv("line", { x1: x(fstar), x2: x(fstar), y1: T, y2: H - B, stroke: "var(--fstar)", "stroke-width": 2 },
        sv("title", { text: `tipping point f* = ${fmt(fstar)}` })));
    }
    return svg;
  }

  // ------------------------------------------------------------ modules
  function modData(src, scope) {
    const mods = (D.results.modules || {})[src] || {};
    return Object.keys(mods).sort().map((m) => {
      const e = mods[m];
      const r = scope === "overall" ? e.overall : (e.by_strategy || {})[scope];
      return { m, dcon: r && r.d_con, ddead: r && r.d_deadlock, use: r && r.usefulness, value: scope === "overall" ? e.value : null };
    });
  }
  function renderModules() {
    const fbox = clear($("#mod-filters")), body = clear($("#mod-body"));
    const mods = D.results.modules || {};
    const has = (s) => mods[s] && Object.keys(mods[s]).length > 0;
    if (!has(S.modSrc)) S.modSrc = ["ABM", "LLM"].find(has) || "ABM";
    fbox.appendChild(select("Data source", ["ABM", "LLM"].map((s) => ({ value: s, label: SOURCE_NAMES[s] + (has(s) ? "" : " (not run yet)"), disabled: !has(s) })),
      S.modSrc, (v) => { S.modSrc = v; S.modScope = "overall"; renderModules(); }));
    if (!has(S.modSrc)) { body.appendChild(empty("Defence module runs: not run yet.")); return; }
    const strats = [...new Set(Object.values(mods[S.modSrc]).flatMap((e) => Object.keys(e.by_strategy || {})))].sort(sortStrat);
    fbox.appendChild(select("Scope", [{ value: "overall", label: "Pooled over social strategies" }]
      .concat(strats.map((s) => ({ value: s, label: `${s} ${sName(s)}` }))), S.modScope, (v) => { S.modScope = v; renderModules(); }));
    const rows = modData(S.modSrc, S.modScope);
    body.appendChild(el("div", { class: "mod-grid" }, el("div", { class: "card" }, modScatter(rows)), modTable(rows)));
  }
  function modScatter(rows) {
    const pts = rows.filter((r) => r.dcon && r.use && isNum(r.dcon.diff) && isNum(r.use.diff));
    if (!pts.length) return empty("No paired estimates for this scope.");
    const W = 420, H = 320, L = 52, R = 14, T = 14, B = 44;
    const xs = pts.flatMap((p) => [p.use.lo, p.use.hi, p.use.diff]).filter(isNum).concat([0]);
    const ys = pts.flatMap((p) => [-p.dcon.lo, -p.dcon.hi, -p.dcon.diff]).filter(isNum).concat([0]);
    const pad = (a, b) => { const d = (b - a) || 0.02; return [a - d * 0.12, b + d * 0.12]; };
    const [x0, x1] = pad(Math.min(...xs), Math.max(...xs)), [y0, y1] = pad(Math.min(...ys), Math.max(...ys));
    const x = (v) => L + ((v - x0) / (x1 - x0)) * (W - L - R), y = (v) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
    const svg = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Defence modules: contamination reduction vs usefulness change" });
    svg.appendChild(sv("rect", { x: x(0), y: T, width: Math.max(0, W - R - x(0)), height: Math.max(0, y(0) - T), fill: "var(--si-lime)", opacity: 0.08 }));
    const ticks = (a, b) => { const st = niceStep((b - a) / 4); const out = []; for (let v = Math.ceil(a / st) * st; v <= b + 1e-12; v += st) out.push(+v.toFixed(10)); return out; };
    for (const v of ticks(y0, y1)) { svg.appendChild(sv("line", { class: "gridline", x1: L, x2: W - R, y1: y(v), y2: y(v) })); svg.appendChild(sv("text", { x: L - 5, y: y(v) + 3, "text-anchor": "end", "font-size": 10, text: trim(v) })); }
    for (const v of ticks(x0, x1)) { svg.appendChild(sv("line", { class: "gridline", y1: T, y2: H - B, x1: x(v), x2: x(v) })); svg.appendChild(sv("text", { x: x(v), y: H - B + 13, "text-anchor": "middle", "font-size": 10, text: trim(v) })); }
    svg.appendChild(sv("line", { x1: L, x2: W - R, y1: y(0), y2: y(0), stroke: "var(--subtle)", "stroke-width": 1 }));
    svg.appendChild(sv("line", { y1: T, y2: H - B, x1: x(0), x2: x(0), stroke: "var(--subtle)", "stroke-width": 1 }));
    svg.appendChild(sv("text", { x: (L + W - R) / 2, y: H - 8, "text-anchor": "middle", "font-size": 11, text: "accuracy change at f = 0 (usefulness)" }));
    svg.appendChild(sv("text", { x: 12, y: (T + H - B) / 2, "text-anchor": "middle", "font-size": 11, transform: `rotate(-90 12 ${(T + H - B) / 2})`, text: "contamination reduction" }));
    if (W - R - x(0) > 96) svg.appendChild(sv("text", { x: W - R - 4, y: T + 12, "text-anchor": "end", "font-size": 10, text: "safer at no cost" }));
    pts.forEach((p, i) => {
      const mi = ["M1", "M2", "M3", "M4", "M5", "M6"].indexOf(p.m);
      const col = mi >= 0 ? `var(--m${mi + 1})` : `var(--o${i % 8})`;
      const g = sv("g", {});
      const cx = x(p.use.diff), cy = y(-p.dcon.diff);
      if (isNum(p.use.lo) && isNum(p.use.hi)) g.appendChild(sv("line", { x1: x(p.use.lo), x2: x(p.use.hi), y1: cy, y2: cy, stroke: col, "stroke-width": 2 }));
      if (isNum(p.dcon.lo) && isNum(p.dcon.hi)) g.appendChild(sv("line", { y1: y(-p.dcon.lo), y2: y(-p.dcon.hi), x1: cx, x2: cx, stroke: col, "stroke-width": 2 }));
      g.appendChild(sv("rect", { x: cx - 5, y: cy - 5, width: 10, height: 10, fill: col, stroke: "var(--surface)", "stroke-width": 1.5 }));
      g.appendChild(sv("text", { x: cx + 8, y: cy - 7, "font-size": 11, "font-weight": 500, style: "fill: var(--fg)", text: p.m }));
      g.appendChild(sv("title", { text: `${p.m} ${mName(p.m)}: contamination change ${ci(p.dcon.diff, p.dcon.lo, p.dcon.hi, 3)}; usefulness ${ci(p.use.diff, p.use.lo, p.use.hi, 3)}` }));
      svg.appendChild(g);
    });
    return svg;
  }
  function niceStep(raw) { const p = Math.pow(10, Math.floor(Math.log10(raw || 1e-3))); const r = raw / p; return (r < 1.5 ? 1 : r < 3.5 ? 2 : r < 7.5 ? 5 : 10) * p; }
  function trim(v) { return Math.abs(v) < 1e-12 ? "0" : String(+v.toPrecision(3)); }
  function modTable(rows) {
    const c = (d) => (d ? ci(d.diff, d.lo, d.hi, 3) : "not run yet");
    const t = el("table", { class: "simple" },
      el("thead", {}, el("tr", {}, ["Module", "Δ contamination", "Δ deadlock", "Usefulness (Δ acc, f=0)", "Value", "Rank", "P(rank 1)"].map((h) => el("th", { text: h })))),
      el("tbody", {}, rows.map((r) => el("tr", {},
        el("td", { title: (D.labels.modules[r.m] || {}).desc || "", text: `${r.m} ${mName(r.m)}` }),
        el("td", { text: c(r.dcon) }), el("td", { text: c(r.ddead) }), el("td", { text: c(r.use) }),
        el("td", { text: r.value ? fmt(r.value.value) : "—" }), el("td", { text: r.value ? String(r.value.rank) : "—" }),
        el("td", { text: r.value ? fmt(r.value.p_first, 3) : "—" })))));
    return el("div", {}, el("div", { class: "tbl-wrap card", style: "padding:0" }, t),
      el("p", { class: "note-sm", text: "Δ = module − no defence, paired by seed (negative Δ contamination is good). Value = contamination reduction ÷ (usefulness loss + 0.01); P(rank 1) is the share of seed resamples in which the module ranks first. Value is only computed for the pooled scope." }));
  }

  // ------------------------------------------------------------ hypotheses
  function renderHypotheses() {
    const fbox = clear($("#hyp-filters")), body = clear($("#hyp-body"));
    const hyps = D.results.hypotheses || [];
    const srcs = [...new Set(hyps.map((h) => h.source))];
    fbox.appendChild(select("Source", [{ value: "all", label: "All sources" }].concat(srcs.map((s) => ({ value: s, label: s }))), S.hypSrc,
      (v) => { S.hypSrc = v; renderHypotheses(); }));
    const counts = {};
    hyps.forEach((h) => { counts[h.verdict] = (counts[h.verdict] || 0) + 1; });
    fbox.appendChild(el("p", { class: "note-sm", style: "align-self:flex-end", text: Object.entries(counts).map(([k, v]) => `${VERDICT_TEXT[k] || k}: ${v}`).join(" · ") }));
    const list = hyps.filter((h) => S.hypSrc === "all" || h.source === S.hypSrc);
    if (!list.length) { body.appendChild(empty("No hypothesis results yet.")); return; }
    for (const h of list) {
      const v = h.verdict || "not run";
      const meta = [];
      if (h.p != null) meta.push(pTxt("p", h.p));
      if (h.p_holm != null) meta.push(pTxt("Holm p", h.p_holm));
      if (h.holm_reject != null) meta.push(h.holm_reject ? "significant after Holm correction" : "not significant after Holm correction");
      const det = el("details", {}, el("summary", { text: "Test and statistic" }), el("p", { class: "note", text: h.test || "—" }));
      if (h.statistic != null) det.appendChild(el("pre", { text: JSON.stringify(h.statistic, null, 1) }));
      if (h.ci != null) det.appendChild(el("pre", { text: "CI: " + JSON.stringify(h.ci) }));
      body.appendChild(el("article", { class: "card hyp" },
        el("header", {}, el("span", { class: "hid", text: h.id }), el("span", { class: "src", text: h.source }),
          el("span", { class: `verdict v-${v.replace(/\s+/g, "-")}`, text: VERDICT_TEXT[v] || v })),
        el("p", { class: "stmt", text: h.statement }),
        meta.length ? el("div", { class: "meta", text: meta.join(" · ") }) : null,
        h.note ? el("p", { class: "note", text: h.note }) : null,
        v !== "not run" || h.statistic != null ? det : null));
    }
  }

  // ------------------------------------------------------------ red team
  function renderRedteam() {
    const body = clear($("#rt-body"));
    const rt = D.results.redteam;
    const h7 = (D.results.hypotheses || []).filter((h) => h.id === "H7");
    if (h7.length) body.appendChild(el("p", { class: "hint", text: "H7 (optimizing searchers find worse attacks than naive ones): " + h7.map((h) => `${h.source} ${VERDICT_TEXT[h.verdict] || h.verdict}`).join("; ") + "." }));
    if (!rt || !Object.keys(rt).length) { body.appendChild(empty("Red-team searches: not run yet.")); return; }
    const grid = el("div", { class: "rt-grid" });
    for (const key of Object.keys(rt).sort()) {
      const [s, topo, k] = key.split("/");
      const ss = Object.keys(rt[key]).sort((a, b) => (Object.keys(SEARCHERS).indexOf(a) + 99 * !(a in SEARCHERS)) - (Object.keys(SEARCHERS).indexOf(b) + 99 * !(b in SEARCHERS)));
      grid.appendChild(el("div", { class: "card" }, el("h3", { text: `${s} ${sName(s)} · ${tName(topo)} · k = ${k}` }), rtSVG(rt[key], ss)));
    }
    body.appendChild(grid);
  }
  function rtSVG(prob, ss) {
    const rowH = 24, L = 112, R = 44, T = 4, W = 320, H = T + ss.length * rowH + 22;
    const x = (v) => L + v * (W - L - R);
    const svg = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Best contamination found per searcher" });
    for (const v of [0, 0.5, 1]) {
      svg.appendChild(sv("line", { class: "gridline", x1: x(v), x2: x(v), y1: T, y2: H - 18 }));
      svg.appendChild(sv("text", { x: x(v), y: H - 6, "text-anchor": "middle", "font-size": 9, text: v.toFixed(1) }));
    }
    ss.forEach((name, i) => {
      const e = prob[name], cy = T + i * rowH + rowH / 2;
      const b = e.best500 || {};
      svg.appendChild(sv("text", { x: L - 6, y: cy + 3, "text-anchor": "end", "font-size": 10, text: SEARCHERS[name] || name }));
      if (isNum(e.q25) && isNum(e.q75)) svg.appendChild(sv("rect", { x: x(e.q25), y: cy - 6, width: Math.max(1, x(e.q75) - x(e.q25)), height: 12, fill: "var(--con)", opacity: 0.3 }));
      if (isNum(b.lo) && isNum(b.hi)) svg.appendChild(sv("line", { x1: x(b.lo), x2: x(b.hi), y1: cy, y2: cy, stroke: "var(--fg)", "stroke-width": 1.4 }));
      if (isNum(b.mean)) {
        const c = sv("rect", { x: x(b.mean) - 4, y: cy - 4, width: 8, height: 8, fill: "var(--con)" });
        const vr = e.vs_random ? `; vs random ${ci(e.vs_random.diff, e.vs_random.lo, e.vs_random.hi, 3)}` : "";
        c.appendChild(sv("title", { text: `${SEARCHERS[name] || name}: mean ${ci(b.mean, b.lo, b.hi, 3)}, median ${fmt(e.median, 3)}, IQR ${fmt(e.q25, 3)}–${fmt(e.q75, 3)}, ${b.n} repeats, ${e.evals} evaluations${vr}` }));
        svg.appendChild(c);
        svg.appendChild(sv("text", { x: W - 4, y: cy + 3, "text-anchor": "end", "font-size": 10, style: "fill: var(--fg)", text: fmt(b.mean) }));
      }
    });
    return svg;
  }

  // ------------------------------------------------------------ replay
  const RP = { data: null, r: 0, timer: null, sel: null, cache: {}, speed: 1 };
  function renderReplayShell() {
    const body = clear($("#replay-body"));
    if (!D.replays.length) { body.appendChild(empty("No run logs exported yet (not run yet).")); return; }
    const opts = D.replays.map((r, i) => ({ value: i, label:
      `${r.strategy} ${sName(r.strategy)} · ${tName(r.topology)} · ${r.n_nodes} agents · f=${fmt(r.f_eff, 3)} · ${r.attack} · ${(r.modules || []).join("+") || "no defence"} · seed ${r.seed} · ${r.rounds} round${r.rounds === 1 ? "" : "s"}` }));
    const top = el("div", { class: "rp-top" }, select("Run", opts, 0, (i) => loadReplay(i)));
    body.appendChild(top);
    body.appendChild(el("div", { id: "rp-main" }));
    loadReplay(0);
  }
  async function loadReplay(i) {
    stop();
    const entry = D.replays[i];
    const main = clear($("#rp-main"));
    main.appendChild(el("p", { class: "note-sm", text: "Loading run…" }));
    try {
      RP.data = RP.cache[entry.run_id] || (RP.cache[entry.run_id] = await getJSON(entry.file));
    } catch (e) {
      clear(main).appendChild(empty(`Could not load ${entry.file}.`));
      return;
    }
    RP.r = 0; RP.sel = null;
    buildReplay();
  }
  function buildReplay() {
    const d = RP.data, main = clear($("#rp-main"));
    const N = d.n_nodes, nr = d.rounds.length;
    const comm = (D.labels.strategies[d.config.strategy] || {}).comm || "graph";
    const rad = Math.max(1.4, Math.min(6.5, 16 / Math.sqrt(N)));
    const P = (v) => 8 + v * 84;
    const svg = sv("svg", { viewBox: "0 0 100 100", role: "group", "aria-label": `Network of ${N} agents` });
    for (const [u, v] of d.edges) {
      svg.appendChild(sv("line", { class: "edge" + (comm === "graph" ? "" : " dim"), x1: P(d.nodes[u].x), y1: P(1 - d.nodes[u].y),
        x2: P(d.nodes[v].x), y2: P(1 - d.nodes[v].y), "stroke-width": N > 60 ? 0.15 : 0.35 }));
    }
    const att = new Set(d.attackers), un = new Set(d.uninformed);
    RP.nodes = d.nodes.map((n) => {
      const cx = P(n.x), cy = P(1 - n.y);
      const g = sv("g", { class: "node", tabindex: 0, role: "button" });
      // agents are square tiles; compromised agents carry a dashed vermilion frame
      const sq = (r, a) => sv("rect", Object.assign({ x: cx - r, y: cy - r, width: 2 * r, height: 2 * r }, a));
      g.appendChild(sq(rad + 1.9, { class: "ring" }));
      if (att.has(n.id)) g.appendChild(sq(rad + 0.9, { fill: "none", stroke: "var(--si-vermilion)", "stroke-width": Math.max(0.45, rad * 0.2), "stroke-dasharray": `${rad * 0.45} ${rad * 0.3}` }));
      const body = sq(rad * 0.9, { class: "body", stroke: un.has(n.id) ? "var(--si-subtle)" : "none", "stroke-width": 0.3, "stroke-dasharray": un.has(n.id) ? "0.6 0.4" : null });
      const label = rad >= 3 ? sv("text", { x: cx, y: cy + rad * 0.36, "text-anchor": "middle", "font-size": rad * 1.0, "font-weight": 600, "pointer-events": "none" }) : null;
      g.append(body); if (label) g.appendChild(label);
      const show = () => { RP.hover = n.id; renderAgent(); };
      g.addEventListener("mouseenter", show);
      g.addEventListener("focus", show);
      g.addEventListener("mouseleave", () => { RP.hover = null; renderAgent(); });
      g.addEventListener("blur", () => { RP.hover = null; renderAgent(); });
      g.addEventListener("click", () => { RP.sel = RP.sel === n.id ? null : n.id; paint(); renderAgent(); });
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); RP.sel = RP.sel === n.id ? null : n.id; paint(); renderAgent(); } });
      svg.appendChild(g);
      return { g, body, label, id: n.id };
    });

    const slider = el("input", { type: "range", min: 0, max: Math.max(0, nr - 1), value: 0, step: 1, "aria-label": "Round", disabled: nr < 2 });
    slider.addEventListener("input", () => { stop(); RP.r = +slider.value; paint(); });
    const play = el("button", { type: "button", text: "Play", disabled: nr < 2, "aria-label": "Play or pause" });
    play.addEventListener("click", () => (RP.timer ? stop() : start()));
    const back = el("button", { type: "button", text: "◀ Step", disabled: nr < 2, "aria-label": "Previous round" });
    back.addEventListener("click", () => { stop(); RP.r = Math.max(0, RP.r - 1); paint(); });
    const fwd = el("button", { type: "button", text: "Step ▶", disabled: nr < 2, "aria-label": "Next round" });
    fwd.addEventListener("click", () => { stop(); RP.r = Math.min(nr - 1, RP.r + 1); paint(); });
    const speed = el("select", { "aria-label": "Speed", disabled: nr < 2 }, [["0.5", "0.5×"], ["1", "1×"], ["2", "2×"]].map(([v, t]) => el("option", { value: v, text: t, selected: +v === RP.speed })));
    speed.addEventListener("change", () => { RP.speed = +speed.value; if (RP.timer) { stop(); start(); } });
    const roundLbl = el("span", { class: "rp-round", "aria-live": "polite" });
    RP.ui = { slider, play, roundLbl };

    const legend = el("div", { class: "legend" }, d.option_ids.map((o, i) => el("span", {},
      el("i", { class: "dot", style: `background:${optColor(i)}` }), `Option ${o}`,
      i === d.correct ? el("span", { class: "tag correct", text: "correct" }) : null,
      i === d.target ? el("span", { class: "tag target", text: "attackers' target" }) : null)),
      el("span", {}, el("i", { class: "dot", style: "background:var(--abstain)" }), "abstain / no valid reply"),
      el("span", {}, el("i", { class: "dot att" }), "compromised agent"),
      d.uninformed && d.uninformed.length ? el("span", {}, el("i", { class: "dot", style: "outline:1px dashed var(--si-subtle);outline-offset:-1px" }), "uninformed (dashed edge)") : null);
    const commNote = { board: "This strategy coordinates through a shared board, not along edges; edges (dashed) show the run's graph for reference.",
      broadcast: "Leaders broadcast to every agent; edges (dashed) show the run's graph for reference.",
      none: "Agents answer independently; edges (dashed) are not used for communication." }[comm];

    const stage = el("div", { class: "rp-stage" }, svg,
      el("div", { class: "rp-ctrl" }, back, play, fwd, slider, roundLbl, speed), legend,
      commNote ? el("p", { class: "note-sm", text: commNote }) : null,
      nr < 2 ? el("p", { class: "note-sm", text: "This run has a single round, so there is nothing to animate." }) : null);
    const side = el("div", { class: "rp-side" }, runCard(d), el("div", { class: "card", id: "rp-round" }), el("div", { class: "card", id: "rp-agent" }));
    main.appendChild(el("div", { class: "rp-grid" }, stage, side));
    paint();
    renderAgent();
  }
  function runCard(d) {
    const c = d.config, m = d.metrics || {};
    const kv = [["Run id", d.run_id], ["Strategy", `${c.strategy} ${sName(c.strategy)}`], ["Topology", tName(c.topology)],
      ["Agents", String(d.n_nodes)], ["Compromised", d.attackers.length ? d.attackers.map((i) => d.displays[i] || i).join(", ") + ` (f = ${fmt(d.f_eff, 3)})` : "none (f = 0)"],
      ["Attack", d.attackers.length ? `${c.attack} ${aName(c.attack)}` : "—"], ["Defences", (c.modules || []).map((x) => `${x} ${mName(x)}`).join(", ") || "none"],
      ["Model", (c.models || []).map((x) => x.split(":").slice(1).join(":") || x).join(", ")], ["Seed", String(c.seed)],
      ["Final accuracy", fmt(m.acc)], ["Final contamination", fmt(m.con)],
      ["Group decision", m.group_correct ? "correct" : m.group_target ? "attackers' target" : m.group_correct === false ? "not correct" : "—"],
      ["Deadlock", m.deadlock == null ? "—" : m.deadlock ? "yes" : "no"], ["Valid replies", fmt(m.valid_rate)]];
    return el("div", { class: "card" }, el("h3", { text: "Run" }), el("dl", { class: "kv" }, kv.flatMap(([k, v]) => [el("dt", { text: k }), el("dd", { text: v })])),
      el("p", { class: "note-sm", text: "Final metrics are copied from the run log; they use the strategy's own final rule (for example majority for S1)." }));
  }
  function paint() {
    const d = RP.data, R = d.rounds[RP.r];
    RP.nodes.forEach((n) => {
      const a = R.agents[n.id];
      const c = a ? a.c : -1;
      n.body.setAttribute("fill", optColor(c));
      if (n.label) { n.label.textContent = c >= 0 ? d.option_ids[c] : "–"; n.label.setAttribute("style", `fill:${optText(c)}`); }
      n.g.classList.toggle("sel", RP.sel === n.id);
      n.g.setAttribute("aria-label", `${d.displays[n.id] || "agent " + n.id}, ${a ? a.role : "no reply"}, chose ${c >= 0 ? d.option_ids[c] : "nothing"}`);
    });
    RP.ui.slider.value = RP.r;
    RP.ui.roundLbl.textContent = `Round ${R.round + 1} of ${d.rounds.length}`;
    const box = clear($("#rp-round"));
    const tot = R.honest_counts.reduce((a, b) => a + b, 0) + R.honest_abstain;
    box.appendChild(el("h3", { text: `Honest agents in round ${R.round + 1}` }));
    const stack = el("div", { class: "stack", role: "img", "aria-label": "Honest agents' choices this round" });
    R.honest_counts.forEach((k, i) => { if (k > 0) stack.appendChild(el("div", { style: `flex:${k};background:${optColor(i)};color:${optText(i)}`, title: `Option ${d.option_ids[i]}: ${k}`, text: `${d.option_ids[i]} ${k}` })); });
    if (R.honest_abstain > 0) stack.appendChild(el("div", { style: `flex:${R.honest_abstain};background:var(--abstain)`, text: `– ${R.honest_abstain}` }));
    box.appendChild(stack);
    box.appendChild(el("p", { class: "note-sm", text: tot ? `Choosing the correct option (${d.option_ids[d.correct]}): ${fmt(R.share_correct)} · choosing the attackers' target (${d.option_ids[d.target]}): ${fmt(R.share_target)}` : "No honest agents." }));
    renderAgent();
  }
  function renderAgent() {
    const box = document.getElementById("rp-agent");
    if (!box || !RP.data) return;
    clear(box);
    const id = RP.hover != null ? RP.hover : RP.sel;
    if (id == null) { box.append(el("h3", { text: "Agent" }), el("p", { class: "note-sm", text: "Hover, focus or tap a node to read what that agent said in this round." })); return; }
    const d = RP.data, a = d.rounds[RP.r].agents[id];
    box.appendChild(el("h3", { text: `${d.displays[id] || "agent " + id}${d.attackers.includes(id) ? " (compromised)" : d.uninformed.includes(id) ? " (uninformed)" : ""}` }));
    if (!a) { box.appendChild(el("p", { class: "note-sm", text: "No turn logged for this agent in this round." })); return; }
    box.appendChild(el("dl", { class: "kv" }, el("dt", { text: "Role" }), el("dd", { text: a.role || "—" }),
      el("dt", { text: "Choice" }), el("dd", { text: a.c >= 0 ? d.option_ids[a.c] + (a.c === d.correct ? " (correct)" : a.c === d.target ? " (attackers' target)" : "") : "abstain" }),
      el("dt", { text: "Confidence" }), el("dd", { text: fmt(a.conf) }),
      el("dt", { text: "Flags" }), el("dd", { text: [a.rev ? "choice reverted by a rule" : null, a.err ? "invalid reply" : null, a.refusal ? "refusal" : null].filter(Boolean).join(", ") || "none" })));
    box.appendChild(el("p", { class: "msg", text: a.msg ? `“${a.msg}”` : "(no message)" }));
    if (a.claims && a.claims.length) {
      box.appendChild(el("ul", { class: "claims" }, a.claims.map((c) => el("li", { text: c }))));
      if (a.n_claims > a.claims.length) box.appendChild(el("p", { class: "note-sm", text: `+${a.n_claims - a.claims.length} more claims` }));
    }
  }
  function start() {
    const d = RP.data;
    if (!d || d.rounds.length < 2) return;
    if (RP.r >= d.rounds.length - 1) RP.r = 0;
    paint();
    RP.ui.play.textContent = "Pause";
    RP.timer = setInterval(() => {
      if (RP.r >= RP.data.rounds.length - 1) { stop(); return; }
      RP.r += 1; paint();
    }, 1400 / RP.speed);
  }
  function stop() {
    if (RP.timer) clearInterval(RP.timer);
    RP.timer = null;
    if (RP.ui && RP.ui.play) RP.ui.play.textContent = "Play";
  }

  // ------------------------------------------------------------ figures and data
  function renderFigures() {
    const body = clear($("#fig-body"));
    const figs = D.results.figures || {};
    const names = Object.keys(figs).sort();
    if (!names.length) { body.appendChild(empty("No figures exported yet.")); return; }
    for (const n of names) {
      const f = figs[n], cap = FIG_CAPTIONS[n] || n;
      if (f.src) body.appendChild(el("figure", {}, el("a", { href: f.src, target: "_blank", rel: "noopener" },
        el("img", { src: f.src, alt: cap, loading: "lazy" })), el("figcaption", { text: cap })));
      else body.appendChild(el("figure", {}, el("div", { class: "empty", style: "border:0;border-radius:0", text: f.status === "not exported" ? "Not exported" : "Not run yet" }),
        el("figcaption", { text: `${cap} (${f.status || "not run yet"})` })));
    }
  }
  function renderData() {
    const body = clear($("#data-body"));
    const m = D.manifest || {}, meta = D.results.meta || {};
    const kv = [["Exported", m.exported], ["Results file", m.results_file], ["Results generated", meta.generated],
      ["Calibrated", meta.calibrated ? "yes" : "no"], ["ABM parameters", meta.params ? `${meta.params.path} (sha256 ${String(meta.params.sha256).slice(0, 12)}…)` : "defaults"],
      ["Bootstrap resamples", `cells ${meta.boot ?? "—"}, tipping ${meta.tip_boot ?? "—"}, hypotheses ${meta.hyp_boot ?? "—"}; Mantel permutations ${meta.perms ?? "—"}`],
      ["Replays exported", String(D.replays.length)]];
    if (meta.llm_primary_model) kv.push(["Primary LLM", meta.llm_primary_model]);
    body.appendChild(el("div", { class: "card" }, el("dl", { class: "kv" }, kv.flatMap(([k, v]) => [el("dt", { text: k }), el("dd", { text: v == null ? "—" : String(v) })]))));
    const inputs = meta.inputs || {};
    if (Object.keys(inputs).length) {
      body.appendChild(el("div", { class: "tbl-wrap", style: "margin-top:10px" }, el("table", { class: "simple" },
        el("thead", {}, el("tr", {}, ["Input", "Path", "SHA-256"].map((h) => el("th", { text: h })))),
        el("tbody", {}, Object.entries(inputs).map(([k, v]) => el("tr", {}, el("td", { text: k }), el("td", { text: v.path }),
          el("td", { class: "mono", text: v.missing ? "not run yet (missing)" : String(v.sha256).slice(0, 16) + "…" })))))));
    }
    body.appendChild(el("p", { class: "note-sm" }, "Raw files: ",
      ["data/manifest.json", "data/results.json", "data/cells.json", "data/labels.json", "data/replays/index.json"]
        .flatMap((f, i) => [i ? " · " : "", el("a", { href: f, text: f })])));
  }

  // ------------------------------------------------------------ boot
  async function boot() {
    renderCast();
    heroSwarm();
    try {
      const [manifest, results, labels] = await Promise.all([getJSON("data/manifest.json"), getJSON("data/results.json"), getJSON("data/labels.json")]);
      Object.assign(D, { manifest, results, labels });
    } catch (e) {
      clear($("#status")).appendChild(el("div", { class: "banner" }, el("strong", { text: "No data found." }),
        el("p", { text: "Run `hiveguard site` to build data/, and serve this folder over HTTP." })));
      return;
    }
    renderStatus();
    renderHypotheses();
    renderModules();
    renderRedteam();
    renderFigures();
    renderData();
    const [cells, replays] = await Promise.all([getJSON("data/cells.json", true), getJSON("data/replays/index.json", true)]);
    D.cells = cells || {};
    D.replays = replays || [];
    setSource(SOURCES.find((s) => cellsFor(s)) || "ABM");
    renderMain();
    renderReplayShell();
    renderData();
  }
  boot();
})();

"""Build the Apart hackathon report (.docx) from paper/paper.md.

Fills the official template (paper/template.docx): keeps its styles, fonts,
page setup, title block and footnote; removes the italic guidance text and the
"How to use this template" box; and writes the paper's sections into the
template's skeleton order.

Usage:
    .venv/bin/python paper/build_docx.py
    .venv/bin/python paper/build_docx.py --md paper/paper.md \
        --template paper/template.docx --out paper/SwarmImmunity_report.docx
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, Twips
from docx.table import Table
from docx.text.paragraph import Paragraph

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
REPO_URL = "https://github.com/dhairya-pandya/AIAF-SwarmAlignment"
REPO_BLOB = REPO_URL + "/blob/main/"

BODY_FONT = "Old Standard TT"
CODE_FONT = "Courier New"
LINK_COLOR = "1155CC"
TABLE_BORDER = "BFBFBF"
TABLE_HEADER_FILL = "F2F2F2"
TEXT_WIDTH_IN = 6.5
TEXT_WIDTH_DXA = 9360

LIMITATIONS_APPENDIX_HEADING = "Limitations and Dual-Use / Ethical Considerations"
CODE_AND_DATA = [
    "**Code, data and replay:** [{0}]({0}). Every LLM call is in the committed cache, and all logged runs replay "
    "byte-for-byte without an API key (`python -m hiveguard.run replay <run_id>`). "
    "**Interactive results:** [https://swarm-immunity.vercel.app](https://swarm-immunity.vercel.app)".format(REPO_URL),
]


# ----------------------------------------------------------------------------
# Markdown parsing
# ----------------------------------------------------------------------------

@dataclass
class Block:
    kind: str  # para | h3 | h4 | list | table | figure | quote | todo
    text: str = ""
    items: list = field(default_factory=list)  # list: (level, ordered, text)
    rows: list = field(default_factory=list)  # table: list of row cell lists
    path: str = ""  # figure
    width: float | None = None  # figure width in inches
    caption: str = ""  # figure/table caption


@dataclass
class Section:
    title: str
    blocks: list


@dataclass
class Paper:
    title: str
    front: list  # raw lines before the first "## "
    sections: list  # list[Section]


LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
IMG_RE = re.compile(r"^!\[(.*)\]\(([^)\s]+)\)\s*(\{[^}]*\})?\s*$")
FIGPH_RE = re.compile(r"^\[FIGURE:\s*([^|\]]+?)\s*(?:\|\s*(.*?))?\s*\]\s*(\{[^}]*\})?\s*$")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
WIDTH_RE = re.compile(r"width\s*=\s*([\d.]+)\s*(in|cm)?")
NOTE_RE = re.compile(r"^\*\(.*\)\*$")  # "*(150-250 words, written last.)*" editorial notes


def _parse_width(attr: str | None) -> float | None:
    if not attr:
        return None
    m = WIDTH_RE.search(attr)
    if not m:
        return None
    val = float(m.group(1))
    return val / 2.54 if m.group(2) == "cm" else val


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells, cur, in_code, in_math = [], "", False, False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            cur += "|"
            i += 2
            continue
        if ch == "`":
            in_code = not in_code
        elif ch == "$" and not in_code:
            in_math = not in_math
        if ch == "|" and not in_code and not in_math:
            cells.append(cur.strip())
            cur = ""
        else:
            cur += ch
        i += 1
    cells.append(cur.strip())
    return cells


def parse_blocks(lines: list[str]) -> list[Block]:
    blocks: list[Block] = []
    i, n = 0, len(lines)
    pending_table_caption = ""
    while i < n:
        line = lines[i].rstrip("\n")
        s = line.strip()
        if not s or s in ("---", "***", "___"):
            i += 1
            continue
        if s.startswith("#### "):
            blocks.append(Block("h4", s[5:].strip()))
            i += 1
            continue
        if s.startswith("### "):
            blocks.append(Block("h3", s[4:].strip()))
            i += 1
            continue
        m = IMG_RE.match(s)
        if m:
            blocks.append(Block("figure", path=m.group(2), caption=m.group(1).strip(),
                                width=_parse_width(m.group(3))))
            i += 1
            continue
        m = FIGPH_RE.match(s)
        if m:
            blocks.append(Block("figure", path=m.group(1).strip(), caption=(m.group(2) or "").strip(),
                                width=_parse_width(m.group(3))))
            i += 1
            continue
        if s.startswith("Table:") and i + 1 < n and lines[i + 1].strip().startswith("|"):
            pending_table_caption = s[len("Table:"):].strip()
            i += 1
            continue
        if s.startswith("|") and i + 1 < n and TABLE_SEP_RE.match(lines[i + 1]):
            rows = [_split_row(s)]
            i += 2
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_split_row(lines[i]))
                i += 1
            caption = pending_table_caption
            pending_table_caption = ""
            if not caption and i < n and lines[i].strip().startswith("Table:"):
                caption = lines[i].strip()[len("Table:"):].strip()
                i += 1
            blocks.append(Block("table", rows=rows, caption=caption))
            continue
        if s.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            blocks.append(Block("quote", " ".join(x for x in buf if x)))
            continue
        if LIST_RE.match(line):
            items: list[list] = []
            stack: list[int] = []
            while i < n:
                ln = lines[i].rstrip("\n")
                m = LIST_RE.match(ln)
                if m:
                    indent = len(m.group(1).replace("\t", "    "))
                    while stack and indent < stack[-1]:
                        stack.pop()
                    if not stack or indent > stack[-1]:
                        stack.append(indent)
                    level = len(stack) - 1
                    ordered = m.group(2)[0].isdigit()
                    items.append([level, ordered, m.group(3).strip()])
                    i += 1
                elif ln.strip() and ln.startswith((" ", "\t")) and items:
                    items[-1][2] += " " + ln.strip()  # continuation line
                    i += 1
                else:
                    break
            blocks.append(Block("list", items=[tuple(x) for x in items]))
            continue
        # paragraph: gather until a blank line or another block starts
        buf = [s]
        i += 1
        while i < n:
            t = lines[i].strip()
            if (not t or t.startswith(("#", "|", ">", "![", "[FIGURE:")) or LIST_RE.match(lines[i])):
                break
            buf.append(t)
            i += 1
        text = " ".join(buf)
        if NOTE_RE.match(text):
            continue  # editorial note to the author, not paper content
        blocks.append(Block("para", text))
    return blocks


def parse_markdown(text: str) -> Paper:
    lines = text.splitlines()
    title = ""
    front: list[str] = []
    sections: list[Section] = []
    cur_title, cur_lines = None, []
    for line in lines:
        if line.startswith("# ") and not title and cur_title is None:
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            if cur_title is not None:
                sections.append(Section(cur_title, parse_blocks(cur_lines)))
            cur_title, cur_lines = line[3:].strip(), []
            continue
        if cur_title is None:
            front.append(line)
        else:
            cur_lines.append(line)
    if cur_title is not None:
        sections.append(Section(cur_title, parse_blocks(cur_lines)))
    return Paper(title, front, sections)


def author_line(front: list[str]) -> str:
    """'**Name**, Long Affiliation (ACR) City' -> 'Name, ACR City'."""
    for line in front:
        m = re.match(r"^\*\*(.+?)\*\*\s*,?\s*(.*)$", line.strip())
        if not m:
            continue
        name, aff = m.group(1).strip(), m.group(2).strip()
        a = re.search(r"\(([A-Z][A-Za-z&]+)\)\s*(.*)$", aff)
        if a:
            aff = (a.group(1) + " " + a.group(2)).strip()
        return f"{name}, {aff}" if aff else name
    return ""


# ----------------------------------------------------------------------------
# Citations
# ----------------------------------------------------------------------------

CITE_PART_RE = re.compile(r"^([A-Z]+)(\d+)(?:\s*[–-]\s*([A-Z]+)?(\d+))?$")


def expand_cite(inner: str, cite_map: dict) -> list[str] | None:
    """Return the list of IDs in a bracket group, or None if it is not a citation."""
    ids: list[str] = []
    for part in inner.split(","):
        m = CITE_PART_RE.match(part.strip())
        if not m:
            return None
        pre, a, pre2, b = m.group(1), int(m.group(2)), m.group(3), m.group(4)
        if b is None:
            ids.append(f"{pre}{a}")
        else:
            if pre2 and pre2 != pre:
                return None
            ids.extend(f"{pre}{k}" for k in range(a, int(b) + 1))
    if not ids or any(x not in cite_map for x in ids):
        return None
    return ids


def compress_numbers(nums: list[int]) -> str:
    nums = sorted(set(nums))
    out, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        if j - i >= 2:
            out.append(f"{nums[i]}–{nums[j]}")
        else:
            out.extend(str(x) for x in nums[i:j + 1])
        i = j + 1
    return ", ".join(out)


class Citer:
    """Numbers citations in order of first appearance in the output document."""

    def __init__(self, cite_map: dict):
        self.cite_map = cite_map
        self.order: dict[str, int] = {}

    def register_text(self, text: str) -> None:
        text = re.sub(r"`[^`]*`", "", text)
        text = re.sub(r"\$[^$]*\$", "", text)
        for inner in re.findall(r"\[([^\[\]]+)\](?!\()", text):
            ids = expand_cite(inner, self.cite_map)
            for x in ids or []:
                self.order.setdefault(x, len(self.order) + 1)

    def render(self, ids: list[str]) -> str:
        for x in ids:
            self.order.setdefault(x, len(self.order) + 1)
        return "[" + compress_numbers([self.order[x] for x in ids]) + "]"


# ----------------------------------------------------------------------------
# LaTeX -> Unicode
# ----------------------------------------------------------------------------

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ",
    "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π",
    "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
SYMBOLS = {
    "sum": "Σ", "prod": "Π", "int": "∫", "in": "∈", "notin": "∉", "le": "≤", "leq": "≤",
    "ge": "≥", "geq": "≥", "neq": "≠", "ne": "≠", "approx": "≈", "sim": "∼", "propto": "∝",
    "star": "*", "ast": "*", "times": "×", "cdot": "·", "pm": "±", "mp": "∓", "infty": "∞",
    "dots": "…", "ldots": "…", "cdots": "⋯", "to": "→", "rightarrow": "→", "leftarrow": "←",
    "gets": "←", "Rightarrow": "⇒", "Leftarrow": "⇐", "leftrightarrow": "↔", "mapsto": "↦",
    "subset": "⊂", "subseteq": "⊆", "cup": "∪", "cap": "∩", "emptyset": "∅", "forall": "∀",
    "exists": "∃", "partial": "∂", "nabla": "∇", "neg": "¬", "land": "∧", "lor": "∨",
    "mid": "|", "vert": "|", "lVert": "‖", "rVert": "‖", "langle": "⟨", "rangle": "⟩",
    "lfloor": "⌊", "rfloor": "⌋", "lceil": "⌈", "rceil": "⌉", "ell": "ℓ", "circ": "∘",
    "prime": "′", "degree": "°", "%": "%", "{": "{", "}": "}", "_": "_", "&": "&", "#": "#",
    "|": "‖",
}
SPACES = {",": " ", ";": " ", ":": " ", "!": "", " ": " ", "quad": "  ", "qquad": "    "}
OPERATORS = {"arg", "max", "min", "ln", "log", "exp", "sin", "cos", "tan", "lim", "sup", "inf",
             "det", "Pr", "argmax", "argmin", "softmax", "deg", "dim", "ker", "mod", "gcd"}
UPRIGHT_CMDS = {"mathrm", "text", "textrm", "operatorname", "mathsf", "textsf", "mathtt",
                "texttt", "mathbf", "textbf", "boldsymbol", "bm", "textup", "mbox"}
ITALIC_CMDS = {"mathit", "textit", "emph"}
SIZING = {"left", "right", "big", "Big", "bigg", "Bigg", "bigl", "bigr", "Bigl", "Bigr",
          "biggl", "biggr", "middle", "displaystyle", "textstyle", "limits", "nolimits"}
ACCENTS = {"overline": "̄", "bar": "̄", "hat": "̂", "widehat": "̂",
           "tilde": "̃", "widetilde": "̃", "vec": "⃗", "dot": "̇",
           "ddot": "̈"}
RELATIONS = set("=<>≤≥∈∉≠≈∼∝←→⇒⇐↔⊂⊆")
BB = {"1": "𝟙", "R": "ℝ", "N": "ℕ", "Z": "ℤ", "Q": "ℚ", "C": "ℂ", "E": "𝔼", "P": "ℙ"}
CAL_EXC = {"B": "ℬ", "E": "ℰ", "F": "ℱ", "H": "ℋ", "I": "ℐ", "L": "ℒ", "M": "ℳ", "R": "ℛ"}


def _cal(ch: str) -> str:
    if ch in CAL_EXC:
        return CAL_EXC[ch]
    if "A" <= ch <= "Z":
        return chr(0x1D49C + ord(ch) - ord("A"))
    return ch


@dataclass
class MSeg:
    text: str
    italic: bool
    vert: str | None  # None | "sub" | "sup"


class _TexParser:
    def __init__(self, src: str):
        self.s = src
        self.i = 0
        self.prev = ""  # last visible character emitted (for spacing decisions)
        self.prev_cmd = ""

    def peek(self) -> str:
        return self.s[self.i] if self.i < len(self.s) else ""

    def skip_ws(self) -> None:
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def read_cmd(self) -> str:
        self.i += 1  # backslash
        j = self.i
        while j < len(self.s) and self.s[j].isalpha():
            j += 1
        if j == self.i:  # single non-letter command like \, or \{
            name = self.s[self.i:self.i + 1]
            self.i += 1
            return name
        name = self.s[self.i:j]
        self.i = j
        return name

    def read_arg(self, upright: bool, vert: str | None) -> list[MSeg]:
        """Read a {group} or a single token."""
        self.skip_ws()
        if self.peek() == "{":
            self.i += 1
            segs = self.parse(upright, vert, stop="}")
            self.i += 1
            return segs
        return self.parse_token(upright, vert)

    def parse(self, upright: bool, vert: str | None, stop: str | None = None) -> list[MSeg]:
        out: list[MSeg] = []
        while self.i < len(self.s):
            if stop and self.peek() == stop:
                return out
            segs = self.parse_token(upright, vert)
            out.extend(segs)
            vis = "".join(sg.text for sg in segs).strip()
            if vis:
                self.prev = vis[-1]
        return out

    def parse_token(self, upright: bool, vert: str | None) -> list[MSeg]:
        ch = self.peek()
        if ch == "":
            return []
        if ch.isspace():
            self.skip_ws()
            return []
        if ch == "{":
            self.i += 1
            segs = self.parse(upright, vert, stop="}")
            self.i += 1
            return segs
        if ch == "}":  # stray brace
            self.i += 1
            return []
        if ch in "^_":
            self.i += 1
            v = vert or ("sup" if ch == "^" else "sub")
            return [MSeg(sg.text, sg.italic, v) for sg in self.read_arg(upright, v)]
        if ch == "\\":
            return self.parse_command(upright, vert)
        self.i += 1
        if ch in "-+" and vert is None:
            sym = "−" if ch == "-" else "+"
            if self.prev and (self.prev.isalnum() or self.prev in ")]|}′*") :
                return [MSeg(f" {sym} ", False, vert)]
            return [MSeg(sym, False, vert)]
        if ch == "-":
            ch = "−"
        elif ch == "'":
            ch = "′"
        elif ch == "~":
            ch = " "
        elif ch == "$":
            ch = ""
        if ch in RELATIONS and vert is None:
            return [MSeg(f" {ch} ", False, vert)]
        return [MSeg(ch, ch.isalpha() and not upright, vert)]

    def parse_command(self, upright: bool, vert: str | None) -> list[MSeg]:
        name = self.read_cmd()
        if name in SPACES:
            return [MSeg(SPACES[name], False, vert)]
        if name in SIZING:
            self.skip_ws()
            if self.peek() == ".":
                self.i += 1
            return []
        if name in GREEK:
            g = GREEK[name]
            return [MSeg(g, g.islower() and not upright, vert)]
        if name in SYMBOLS:
            sym = SYMBOLS[name]
            if sym in RELATIONS and vert is None:
                return [MSeg(f" {sym} ", False, vert)]
            return [MSeg(sym, False, vert)]
        if name in OPERATORS:
            self.skip_ws()
            nxt = self.peek()
            sep = "" if (nxt in "_^({[|" or nxt == "" or name == "arg" or nxt == "\\") else " "
            pre = " " if (self.prev.isalnum() and self.prev_cmd != "arg") else ""
            self.prev_cmd = name
            return [MSeg(pre + name + sep, False, vert)]
        if name in UPRIGHT_CMDS:
            return [MSeg(sg.text, False, sg.vert) for sg in self.read_arg(True, vert)]
        if name in ITALIC_CMDS:
            return [MSeg(sg.text, True, sg.vert) for sg in self.read_arg(False, vert)]
        if name == "mathbb":
            segs = self.read_arg(True, vert)
            return [MSeg("".join(BB.get(c, c) for c in sg.text), False, sg.vert) for sg in segs]
        if name == "mathcal" or name == "mathscr":
            segs = self.read_arg(True, vert)
            return [MSeg("".join(_cal(c) for c in sg.text), False, sg.vert) for sg in segs]
        if name in ACCENTS:
            segs = self.read_arg(upright, vert)
            mark = ACCENTS[name]
            total = sum(len(sg.text) for sg in segs)
            if total > 1 and mark == "̄":
                mark = "̅"
            return [MSeg("".join(c + mark for c in sg.text), sg.italic, sg.vert) for sg in segs]
        if name in ("frac", "dfrac", "tfrac"):
            num = self.read_arg(upright, vert)
            den = self.read_arg(upright, vert)
            frac = _wrap(num, vert) + [MSeg("/", False, vert)] + _wrap(den, vert)
            self.skip_ws()
            if self.peek() not in ("", "}"):  # more follows: keep the fraction together
                frac = [MSeg("(", False, vert)] + frac + [MSeg(")", False, vert)]
            return frac
        if name == "sqrt":
            arg = self.read_arg(upright, vert)
            return [MSeg("√", False, vert)] + _wrap(arg, vert)
        # unknown command: show its name without the backslash
        return [MSeg(name, False, vert)]


def _wrap(segs: list[MSeg], vert: str | None) -> list[MSeg]:
    txt = "".join(s.text for s in segs).strip()
    segs = _strip_rel_space(segs)
    if len(txt) > 1 and re.search(r"[+−\-\s/·×=]", txt):
        return [MSeg("(", False, vert)] + segs + [MSeg(")", False, vert)]
    return segs


def _strip_rel_space(segs: list[MSeg]) -> list[MSeg]:
    return [MSeg(s.text.strip(" ") if s.text.strip() in RELATIONS else s.text, s.italic, s.vert)
            for s in segs]


def tex_to_segments(src: str) -> list[MSeg]:
    """Convert inline LaTeX math to Unicode segments (text, italic, sub/sup)."""
    segs = _TexParser(src).parse(False, None)
    merged: list[MSeg] = []
    for sg in segs:
        t = sg.text.replace("\\", "").replace("$", "")
        if not t:
            continue
        if merged and merged[-1].italic == sg.italic and merged[-1].vert == sg.vert:
            merged[-1].text += t
        else:
            merged.append(MSeg(t, sg.italic, sg.vert))
    # strip outer whitespace and collapse double spaces
    for sg in merged:
        sg.text = re.sub(r" {2,}", " ", sg.text)
    if merged:
        merged[0].text = merged[0].text.lstrip()
        merged[-1].text = merged[-1].text.rstrip()
    return [m for m in merged if m.text]


def tex_to_text(src: str) -> str:
    return "".join(s.text for s in tex_to_segments(src))


# ----------------------------------------------------------------------------
# Inline markdown -> run specs
# ----------------------------------------------------------------------------

@dataclass
class Fmt:
    bold: bool = False
    italic: bool = False
    code: bool = False
    vert: str | None = None
    link: str | None = None
    highlight: bool = False

    def but(self, **kw) -> "Fmt":
        f = copy.copy(self)
        for k, v in kw.items():
            setattr(f, k, v)
        return f


INLINE_RE = re.compile(
    r"(?P<code>`+)(?P<codetext>.+?)(?P=code)"
    r"|\$(?!\$)(?P<math>[^$]+?)\$"
    r"|\[(?P<ltext>[^\]]+)\]\((?P<lurl>[^)\s]+)\)"
    r"|\*\*(?P<bold>.+?)\*\*"
    r"|(?<![\w*])\*(?!\s)(?P<ital>.+?)(?<!\s)\*(?!\*)"
    r"|(?<!\w)_(?!\s)(?P<ital2>.+?)(?<!\s)_(?!\w)"
    r"|\[(?P<br>[^\[\]]+)\]"
)
ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|$<>])")
PLACEHOLDER_RE = re.compile(r"^(TBD|TODO|Author to write|missing figure)", re.I)


def resolve_link(url: str) -> str:
    if re.match(r"^[a-z]+://", url) or url.startswith("mailto:"):
        return url
    rel = url
    while rel.startswith("../"):
        rel = rel[3:]
    rel = rel.lstrip("./")
    return REPO_BLOB + rel


def parse_inline(text: str, fmt: Fmt, citer: Citer | None) -> list[tuple[str, Fmt]]:
    out: list[tuple[str, Fmt]] = []
    pos = 0
    for m in INLINE_RE.finditer(text):
        if m.start() > pos:
            out.append((ESCAPE_RE.sub(r"\1", text[pos:m.start()]), fmt))
        pos = m.end()
        if m.group("code"):
            out.append((m.group("codetext").strip(), fmt.but(code=True)))
        elif m.group("math") is not None:
            for sg in tex_to_segments(m.group("math")):
                # non-breaking spaces keep an inline formula on one line
                out.append((sg.text.replace(" ", "\u00a0"), fmt.but(italic=fmt.italic or sg.italic, vert=sg.vert)))
        elif m.group("ltext") is not None:
            out.extend(parse_inline(m.group("ltext"), fmt.but(link=resolve_link(m.group("lurl"))), citer))
        elif m.group("bold") is not None:
            out.extend(parse_inline(m.group("bold"), fmt.but(bold=True), citer))
        elif m.group("ital") is not None:
            out.extend(parse_inline(m.group("ital"), fmt.but(italic=True), citer))
        elif m.group("ital2") is not None:
            out.extend(parse_inline(m.group("ital2"), fmt.but(italic=True), citer))
        else:
            inner = m.group("br")
            ids = expand_cite(inner, citer.cite_map) if citer else None
            if ids:
                out.append((citer.render(ids), fmt))
            else:
                f2 = fmt.but(highlight=True) if PLACEHOLDER_RE.match(inner.strip()) else fmt
                out.append(("[", f2))
                out.extend(parse_inline(inner, f2, citer))
                out.append(("]", f2))
    if pos < len(text):
        out.append((ESCAPE_RE.sub(r"\1", text[pos:]), fmt))
    return [(t, f) for t, f in out if t]


# ----------------------------------------------------------------------------
# docx helpers
# ----------------------------------------------------------------------------

def _set_fonts(rpr_parent, font: str) -> None:
    rpr = rpr_parent.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(a), font)


def add_hyperlink_container(paragraph: Paragraph, url: str):
    r_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
    h = OxmlElement("w:hyperlink")
    h.set(qn("r:id"), r_id)
    paragraph._p.append(h)
    return h


def write_runs(paragraph: Paragraph, runs: list[tuple[str, Fmt]], size: float | None = None) -> None:
    link_el, link_url = None, None
    for text, f in runs:
        run = paragraph.add_run(text)
        _set_fonts(run._r, CODE_FONT if f.code else BODY_FONT)
        if f.code:
            run.font.size = Pt((size or 11) - 1.5)
        elif size:
            run.font.size = Pt(size)
        if f.bold:
            run.bold = True
        if f.italic:
            run.italic = True
        if f.vert == "sub":
            run.font.subscript = True
        elif f.vert == "sup":
            run.font.superscript = True
        if f.highlight:
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        if f.link:
            run.font.underline = True
            run.font.color.rgb = docx.shared.RGBColor.from_string(LINK_COLOR)
            if link_el is None or link_url != f.link:
                link_el = add_hyperlink_container(paragraph, f.link)
                link_url = f.link
            link_el.append(run._r)
        else:
            link_el, link_url = None, None


def ensure_list_numbering(document) -> dict:
    """Add one bullet and one decimal abstractNum to the template's numbering part."""
    numbering = document.part.numbering_part.element
    existing = [int(x) for x in numbering.xpath("./w:abstractNum/@w:abstractNumId")]
    base = max(existing + [0]) + 1
    bullets = ["•", "–", "▪", "•", "–", "▪", "•", "–", "▪"]

    def make_abs(abs_id: int, ordered: bool):
        a = OxmlElement("w:abstractNum")
        a.set(qn("w:abstractNumId"), str(abs_id))
        mlt = OxmlElement("w:multiLevelType")
        mlt.set(qn("w:val"), "hybridMultilevel")
        a.append(mlt)
        for lvl in range(9):
            el = OxmlElement("w:lvl")
            el.set(qn("w:ilvl"), str(lvl))
            st = OxmlElement("w:start")
            st.set(qn("w:val"), "1")
            fmt = OxmlElement("w:numFmt")
            fmt.set(qn("w:val"), "decimal" if ordered else "bullet")
            txt = OxmlElement("w:lvlText")
            txt.set(qn("w:val"), f"%{lvl + 1}." if ordered else bullets[lvl])
            jc = OxmlElement("w:lvlJc")
            jc.set(qn("w:val"), "left")
            ppr = OxmlElement("w:pPr")
            ind = OxmlElement("w:ind")
            ind.set(qn("w:left"), str(360 + 360 * lvl + 360))
            ind.set(qn("w:hanging"), "360")
            ppr.append(ind)
            rpr = OxmlElement("w:rPr")
            rf = OxmlElement("w:rFonts")
            for at in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
                rf.set(qn(at), BODY_FONT)
            rpr.append(rf)
            for child in (st, fmt, txt, jc, ppr, rpr):
                el.append(child)
            a.append(el)
        return a

    first_num = numbering.find(qn("w:num"))
    for abs_el in (make_abs(base, False), make_abs(base + 1, True)):
        if first_num is not None:
            first_num.addprevious(abs_el)
        else:
            numbering.append(abs_el)
    state = {"numbering": numbering, "bullet_abs": base, "decimal_abs": base + 1}
    state["bullet_num"] = _new_num(state, base, restart=False)
    return state


def _new_num(state: dict, abs_id: int, restart: bool = True) -> int:
    numbering = state["numbering"]
    ids = [int(x) for x in numbering.xpath("./w:num/@w:numId")]
    num_id = max(ids + [0]) + 1
    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(num_id))
    an = OxmlElement("w:abstractNumId")
    an.set(qn("w:val"), str(abs_id))
    num.append(an)
    if restart:
        for lvl in range(9):
            ov = OxmlElement("w:lvlOverride")
            ov.set(qn("w:ilvl"), str(lvl))
            so = OxmlElement("w:startOverride")
            so.set(qn("w:val"), "1")
            ov.append(so)
            num.append(ov)
    numbering.append(num)
    return num_id


def set_num(paragraph: Paragraph, num_id: int, level: int) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    numpr = OxmlElement("w:numPr")
    il = OxmlElement("w:ilvl")
    il.set(qn("w:val"), str(level))
    ni = OxmlElement("w:numId")
    ni.set(qn("w:val"), str(num_id))
    numpr.append(il)
    numpr.append(ni)
    ppr.insert(0, numpr) if ppr.find(qn("w:pStyle")) is None else ppr.find(qn("w:pStyle")).addnext(numpr)


def _cell_border_xml(tag: str, color: str, sz: int = 4):
    el = OxmlElement(tag)
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), str(sz))
    el.set(qn("w:space"), "0")
    el.set(qn("w:color"), color)
    return el


TBLPR_ORDER = ["tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize",
               "tblStyleColBandSize", "tblW", "jc", "tblCellSpacing", "tblInd", "tblBorders", "shd",
               "tblLayout", "tblCellMar", "tblLook", "tblCaption", "tblDescription"]


def _sort_children(el, order: list[str]) -> None:
    """Re-order child elements to follow the OOXML schema sequence."""
    rank = {qn("w:" + n): i for i, n in enumerate(order)}
    kids = list(el)
    for k in kids:
        el.remove(k)
    for k in sorted(kids, key=lambda c: rank.get(c.tag, len(order))):
        el.append(k)


def style_table_light(table: Table, widths: list[int]) -> None:
    tbl = table._tbl
    tblPr = tbl.tblPr
    for tag in ("w:tblBorders", "w:tblW", "w:tblLayout"):
        old = tblPr.find(qn(tag))
        if old is not None:
            tblPr.remove(old)
    tw = OxmlElement("w:tblW")
    tw.set(qn("w:w"), str(sum(widths)))
    tw.set(qn("w:type"), "dxa")
    tblPr.append(tw)
    borders = OxmlElement("w:tblBorders")
    for t in ("top", "left", "bottom", "right", "insideH", "insideV"):
        borders.append(_cell_border_xml(f"w:{t}", TABLE_BORDER))
    tblPr.append(borders)
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    tblPr.append(lay)
    _sort_children(tblPr, TBLPR_ORDER)
    grid = tbl.tblGrid
    for gc, w in zip(grid.findall(qn("w:gridCol")), widths):
        gc.set(qn("w:w"), str(w))
    for r_i, row in enumerate(table.rows):
        for c_i, cell in enumerate(row.cells):
            cell.width = Twips(widths[c_i])
            if r_i == 0:
                tcPr = cell._tc.get_or_add_tcPr()
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:color"), "auto")
                shd.set(qn("w:fill"), TABLE_HEADER_FILL)
                tcPr.append(shd)
    # repeat header row across pages
    trPr = table.rows[0]._tr.get_or_add_trPr()
    th = OxmlElement("w:tblHeader")
    th.set(qn("w:val"), "1")
    trPr.append(th)


def _visible_len(md: str) -> int:
    t = re.sub(r"\$([^$]*)\$", lambda m: tex_to_text(m.group(1)), md)
    t = re.sub(r"[*`]", "", t)
    return len(t)


def column_widths(rows: list[list[str]]) -> list[int]:
    ncol = max(len(r) for r in rows)
    # group-label rows (text only in the first cell) should not widen the first column
    body = [r for r in rows[1:] if any(c.strip() for c in r[1:])] or rows   # data rows set the widths
    lens = []
    for c in range(ncol):
        vals = [_visible_len(r[c]) if c < len(r) else 0 for r in body]
        lens.append(max(4, min(max(vals), 80)) ** 0.9)
    total = sum(lens)
    widths = [max(820, int(TEXT_WIDTH_DXA * x / total)) for x in lens]
    if ncol >= 6:   # wide tables: keep the label column from crowding out the numbers
        widths[0] = min(widths[0], int(0.24 * TEXT_WIDTH_DXA))
    scale = TEXT_WIDTH_DXA / sum(widths)
    widths = [int(w * scale) for w in widths]
    widths[-1] += TEXT_WIDTH_DXA - sum(widths)
    return widths


# ----------------------------------------------------------------------------
# Builder
# ----------------------------------------------------------------------------

class Builder:
    def __init__(self, template: Path, md_path: Path, cite_map: dict, ref_texts: dict):
        self.doc = docx.Document(str(template))
        self.md_dir = md_path.parent
        self.citer = Citer(cite_map)
        self.ref_texts = ref_texts
        self.fig_no = 0
        self.table_no = 0
        self.counting = False
        self.words = 0
        self.figs_in_body = 0
        self.missing_figs: list[str] = []
        self.warnings: list[str] = []
        self.body = self.doc.element.body
        self.sectPr = self.body.find(qn("w:sectPr"))
        self._capture_prototypes()
        self.numbering = ensure_list_numbering(self.doc)

    # -- template surgery ---------------------------------------------------
    def _capture_prototypes(self) -> None:
        h2 = h3 = None
        for p in self.doc.paragraphs:
            if p.style.name == "Heading 2" and h2 is None and p.text.strip().startswith("1."):
                h2 = p._p
            if p.style.name == "Heading 3" and h3 is None:
                h3 = p._p
        if h2 is None or h3 is None:
            raise SystemExit("template has no Heading 2 / Heading 3 paragraphs to copy")
        self.h2_proto = copy.deepcopy(h2)
        self.h3_proto = copy.deepcopy(h3)

    def clear_body_after_title(self) -> None:
        children = list(self.body)
        tables = [c for c in children if c.tag == qn("w:tbl")]
        title_tbl = tables[0]
        idx = children.index(title_tbl)
        keep_until = idx + 1  # keep one spacer paragraph after the title block
        for c in children[keep_until + 1:]:
            if c is not self.sectPr:
                self.body.remove(c)

    def fill_title_block(self, title: str, author: str, abstract_blocks: list[Block]) -> None:
        tbl = Table(self.body.findall(qn("w:tbl"))[0], self.doc._body)
        all_ps = [Paragraph(p, tbl._parent) for p in tbl._tbl.iter(qn("w:p"))]
        # Title: replace the text of the first text run, keep the footnote reference
        for p in all_ps:
            if p.style is not None and p.style.name == "Title":
                done = False
                for r in p.runs:
                    if r.text and not done:
                        r.text = title
                        done = True
                    elif r.text:
                        r.text = ""
                break
        # Authors: replace the nested 6-cell author grid with one centred author line
        nested = [t for t in tbl._tbl.iter(qn("w:tbl")) if t is not tbl._tbl]
        author_grid = None
        for t in nested:
            if "Author name" in "".join(t.itertext()):
                author_grid = t
        if author_grid is not None:
            proto_p = author_grid.find(".//" + qn("w:p"))
            new_p = copy.deepcopy(proto_p)
            for r in new_p.findall(qn("w:r")):
                new_p.remove(r)
            author_grid.addprevious(new_p)
            author_grid.getparent().remove(author_grid)
            para = Paragraph(new_p, tbl._parent)
            write_runs(para, [(author, Fmt())], size=12)
        # Abstract: the guidance paragraph inside the abstract box
        target = None
        for p in all_ps:
            if p.text.startswith("Summarize your project"):
                target = p
        if target is None:
            self.warnings.append("abstract placeholder not found in template")
            return
        ppr = target._p.pPr
        if ppr is not None and ppr.find(qn("w:rPr")) is not None:
            u = ppr.find(qn("w:rPr")).find(qn("w:u"))
            if u is not None:
                ppr.find(qn("w:rPr")).remove(u)
        for r in list(target._p):
            if r.tag != qn("w:pPr"):
                target._p.remove(r)
        paras = [b for b in abstract_blocks if b.kind in ("para", "quote")] or [Block("para", "[TBD]")]
        anchor = target._p
        for k, b in enumerate(paras):
            if k == 0:
                p_el = target._p
            else:
                p_el = copy.deepcopy(target._p)
                for r in list(p_el):
                    if r.tag != qn("w:pPr"):
                        p_el.remove(r)
                anchor.addnext(p_el)
                anchor = p_el
            write_runs(Paragraph(p_el, target._parent), parse_inline(b.text, Fmt(), self.citer))

    # -- body emission -----------------------------------------------------
    def _heading(self, proto, text: str) -> None:
        el = copy.deepcopy(proto)
        for tag in ("w:bookmarkStart", "w:bookmarkEnd", "w:hyperlink"):
            for b in el.findall(qn(tag)):
                el.remove(b)
        runs = el.findall(qn("w:r"))
        rpr = copy.deepcopy(runs[0].find(qn("w:rPr"))) if runs else None
        for r in runs:
            el.remove(r)
        self.sectPr.addprevious(el)
        para = Paragraph(el, self.doc._body)
        for t, f in parse_inline(text, Fmt(), self.citer):
            run = para.add_run(t)
            if rpr is not None:
                run._r.insert(0, copy.deepcopy(rpr))
            if f.code:
                _set_fonts(run._r, CODE_FONT)
            if f.italic:
                run.italic = True
            if f.vert == "sub":
                run.font.subscript = True
            elif f.vert == "sup":
                run.font.superscript = True
        if self.counting:
            self.words += len(para.text.split())

    def h2(self, text: str) -> None:
        self._heading(self.h2_proto, text)

    def h3(self, text: str) -> None:
        self._heading(self.h3_proto, text)

    def para(self, text: str, fmt: Fmt | None = None, align=None, size=None,
             space_after: float = 6, indent: float | None = None) -> Paragraph:
        p = self.doc.add_paragraph(style=self.doc.styles["normal"])
        p.paragraph_format.space_after = Pt(space_after)
        if align is not None:
            p.alignment = align
        if indent is not None:
            p.paragraph_format.left_indent = Inches(indent)
        write_runs(p, parse_inline(text, fmt or Fmt(), self.citer), size=size)
        if self.counting:
            self.words += len(p.text.split())
        return p

    def placeholder(self, text: str) -> None:
        p = self.doc.add_paragraph(style=self.doc.styles["normal"])
        p.paragraph_format.space_after = Pt(6)
        write_runs(p, [(text, Fmt(highlight=True))])

    def list_block(self, items: list[tuple]) -> None:
        ordered_nums: dict[int, int] = {}
        for k, (level, ordered, text) in enumerate(items):
            for lv in [x for x in ordered_nums if x > level]:
                del ordered_nums[lv]
            if ordered:
                if level not in ordered_nums:
                    ordered_nums[level] = _new_num(self.numbering, self.numbering["decimal_abs"])
                num_id = ordered_nums[level]
            else:
                ordered_nums.pop(level, None)
                num_id = self.numbering["bullet_num"]
            last = k == len(items) - 1
            p = self.para(text, space_after=6 if last else 2)
            set_num(p, num_id, min(level, 8))

    def table_block(self, b: Block) -> None:
        rows = b.rows
        ncol = max(len(r) for r in rows)
        if b.caption:
            self.table_no += 1
            self.para(f"Table {self.table_no}. {b.caption}", Fmt(italic=True), space_after=3)
        widths = column_widths(rows)
        table = self.doc.add_table(rows=len(rows), cols=ncol)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        style_table_light(table, widths)
        for r_i, row in enumerate(rows):
            for c_i in range(ncol):
                cell = table.cell(r_i, c_i)
                text = row[c_i] if c_i < len(row) else ""
                p = cell.paragraphs[0]
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.0
                write_runs(p, parse_inline(text, Fmt(bold=(r_i == 0)), self.citer), size=9.5)
                if self.counting:
                    self.words += len(p.text.split())
        spacer = self.doc.add_paragraph(style=self.doc.styles["normal"])
        spacer.paragraph_format.space_after = Pt(4)

    def figure_block(self, b: Block) -> None:
        self.fig_no += 1
        if self.counting:
            self.figs_in_body += 1
        path = Path(b.path)
        candidates = [path] if path.is_absolute() else [self.md_dir / path, REPO_ROOT / path]
        found = next((c for c in candidates if c.is_file()), None)
        if found is None:
            self.missing_figs.append(b.path)
            self.para(f"[missing figure: {b.path}]", Fmt(highlight=True), align=WD_ALIGN_PARAGRAPH.CENTER)
        else:
            p = self.doc.add_paragraph(style=self.doc.styles["normal"])
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.keep_with_next = True
            p.add_run().add_picture(str(found), width=Inches(min(b.width or TEXT_WIDTH_IN, TEXT_WIDTH_IN)))
        cap = f"Figure {self.fig_no}." + (f" {b.caption}" if b.caption else "")
        self.para(cap, Fmt(italic=True), align=WD_ALIGN_PARAGRAPH.CENTER, size=10, space_after=8)

    def blocks(self, blocks: list[Block], in_h3: bool = False) -> None:
        for b in blocks:
            if b.kind == "h3":
                if in_h3:
                    self.para(b.text, Fmt(bold=True), space_after=3)
                else:
                    self.h3(b.text)
            elif b.kind == "h4":
                self.para(b.text, Fmt(bold=True), space_after=3)
            elif b.kind == "para":
                txt = b.text.strip()
                if txt.startswith("$$") and txt.endswith("$$") and len(txt) > 4:
                    # display equation: centred on its own line; "\tag{n}" becomes a right-hand number
                    body, tag = txt[2:-2].strip(), ""
                    mt = re.search(r"\\tag\{([^}]*)\}", body)
                    if mt:
                        body, tag = (body[:mt.start()] + body[mt.end():]).strip(), f"\u2003\u2003({mt.group(1)})"
                    self.para(f"${body}${tag}", align=WD_ALIGN_PARAGRAPH.CENTER, space_after=6)
                else:
                    self.para(b.text, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
            elif b.kind == "quote":
                self.para(b.text, Fmt(italic=True), indent=0.4)
            elif b.kind == "list":
                self.list_block(b.items)
            elif b.kind == "table":
                self.table_block(b)
            elif b.kind == "figure":
                self.figure_block(b)
            elif b.kind == "todo":
                self.placeholder(b.text)

    def references(self) -> None:
        ordered = sorted(self.citer.order.items(), key=lambda kv: kv[1])
        for cid, n in ordered:
            src_no = self.citer.cite_map[cid]["number"]
            text = self.ref_texts.get(src_no)
            if text is None:
                self.warnings.append(f"no reference text for {cid} (#{src_no})")
                text = self.citer.cite_map[cid].get("short", cid) + ". " + self.citer.cite_map[cid].get("url", "")
            p = self.doc.add_paragraph(style=self.doc.styles["normal"])
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.left_indent = Inches(0.35)
            p.paragraph_format.first_line_indent = Inches(-0.35)
            runs = [(f"[{n}]\t", Fmt())] + parse_inline(text, Fmt(), None)
            write_runs(p, runs, size=10)
            p.paragraph_format.tab_stops.add_tab_stop(Inches(0.35))


# ----------------------------------------------------------------------------
# Section mapping
# ----------------------------------------------------------------------------

def _norm(title: str) -> str:
    t = re.sub(r"^(appendix\s+[a-z0-9]+[.:]?\s*|\d+(\.\d+)*[.:]?\s*)", "", title.strip(), flags=re.I)
    return t.strip().lower()


def find_section(paper: Paper, pattern: str, exclude: tuple = ()) -> Section | None:
    for s in paper.sections:
        if s in exclude:
            continue
        if re.search(pattern, _norm(s.title)) and not s.title.lower().startswith("appendix"):
            return s
    return None


def split_future_work(blocks: list[Block]) -> tuple[list[Block], list[Block]]:
    """Separate a 'Future work' sub-part (### heading or bold lead-in) from limitations."""
    lim, fut, in_fut = [], [], False
    for b in blocks:
        if b.kind in ("h3", "h4"):
            in_fut = bool(re.search(r"future", b.text, re.I))
            if in_fut:
                continue
        if b.kind == "para" and re.match(r"^\*\*future work[.:]?\*\*", b.text, re.I):
            in_fut = True
        (fut if in_fut else lim).append(b)
    return lim, fut


def plan_document(paper: Paper) -> tuple[list, list[str], list[Block]]:
    """Return an ordered list of ('h2'|'h3'|'blocks'|'todo'|'special', payload) and notes."""
    notes: list[str] = []
    used: set[int] = set()

    def take(pattern: str) -> Section | None:
        s = find_section(paper, pattern)
        if s is not None:
            used.add(id(s))
        return s

    abstract = take(r"^abstract$")
    intro = take(r"introduction")
    related = take(r"related work")
    methods = take(r"^method")
    results = take(r"^result")
    discussion = take(r"^discussion")
    limitations = take(r"limitation")
    conclusion = take(r"conclusion")
    references = take(r"^references?$")
    appendices = [s for s in paper.sections if s.title.lower().startswith("appendix")]
    for a in appendices:
        used.add(id(a))

    plan: list = []

    def section(h2: str, sec: Section | None, missing: str) -> None:
        plan.append(("h2", h2))
        if sec is None:
            plan.append(("todo", missing))
            notes.append(f"no md section for '{h2}'")
        else:
            plan.append(("blocks", sec.blocks))

    plan.append(("count_on", None))
    section("1. Introduction", intro, "[TODO: Introduction: no '## 1. Introduction' section in paper.md]")
    section("2. Related Work", related, "[TODO: Related Work: no matching section in paper.md]")
    section("3. Methods", methods, "[TODO: Methods: no matching section in paper.md]")
    section("4. Results", results, "[TODO: Results: no matching section in paper.md]")

    plan.append(("h2", "5. Discussion and Limitations"))
    if discussion is not None:
        disc_blocks = discussion.blocks
        # a discussion section may itself contain a limitations subsection
        lim_inner, rest = [], []
        if limitations is None:
            cur = rest
            for b in disc_blocks:
                if b.kind == "h3":
                    cur = lim_inner if re.search(r"limitation|future", b.text, re.I) else rest
                    if cur is lim_inner and re.search(r"limitation", b.text, re.I):
                        continue
                cur.append(b)
            disc_blocks = rest
        plan.append(("blocks", disc_blocks))
    else:
        plan.append(("todo", "[TODO: Discussion: no '## Discussion' section in paper.md]"))
        notes.append("no md section for Discussion")
        lim_inner = []
    lim_blocks = limitations.blocks if limitations is not None else lim_inner
    lim_part, fut_part = split_future_work(lim_blocks)
    plan.append(("h3", "Limitations"))
    if lim_part:
        plan.append(("blocks", lim_part))
    else:
        plan.append(("todo", "[TODO: Limitations: no limitations section in paper.md]"))
        notes.append("no md content for Limitations")
    plan.append(("h3", "Future Work"))
    if fut_part:
        plan.append(("blocks", fut_part))
    else:
        plan.append(("todo", "[TODO: Future work: paper.md has no future-work text yet "
                             "(add a 'Future work' subsection or bold lead-in paragraph under §6)]"))
        notes.append("no future-work text in md (TODO placeholder emitted)")

    section("6. Conclusion", conclusion,
            "[TODO: Conclusion: add a '## 7. Conclusion' section to paper.md]")
    plan.append(("count_off", None))

    plan.append(("h2", "Code and Data"))
    plan.append(("blocks", [Block("para", t) for t in CODE_AND_DATA]))

    plan.append(("h2", "References"))
    plan.append(("references", None))

    plan.append(("h2", "Appendix"))
    ethics = [a for a in appendices if re.search(r"dual-use|ethic", a.title, re.I)]
    plan.append(("h3", LIMITATIONS_APPENDIX_HEADING))
    for a in ethics:
        plan.append(("blocks_h3", a.blocks))
    if lim_part:
        plan.append(("blocks_h3", [Block("h4", "Limitations")] + lim_part))
    if not ethics:
        plan.append(("todo", "[TODO: dual-use and ethical considerations: no matching appendix in paper.md]"))
        notes.append("no dual-use/ethics appendix in md")
    for a in appendices:
        if a in ethics:
            continue
        name = re.sub(r"^appendix\s+[a-z0-9]+[.:]?\s*", "", a.title, flags=re.I).strip() or a.title
        plan.append(("h3", name))
        plan.append(("blocks_h3", a.blocks))

    plan.append(("h2", "LLM Usage Statement"))
    plan.append(("todo", "[Author to write]"))

    for s in paper.sections:
        if id(s) not in used:
            notes.append(f"md section '{s.title}' not mapped to a template section (dropped)")
    if references is not None:
        notes.append("md '## References' note replaced by the numbered list from references.md")
    return plan, notes, (abstract.blocks if abstract else [])


def _all_text(blocks: list[Block]) -> list[str]:
    out = []
    for b in blocks:
        if b.kind == "list":
            out.extend(t for _, _, t in b.items)
        elif b.kind == "table":
            out.extend(c for r in b.rows for c in r)
            out.append(b.caption)
        else:
            out.append(b.text)
            out.append(b.caption)
    return out


def load_references(path: Path) -> dict[int, str]:
    refs: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(\d+)\.\s+(.*\S)\s*$", line)
        if m and int(m.group(1)) not in refs:
            refs[int(m.group(1))] = m.group(2)
    return refs


def build(md_path: Path, template: Path, out: Path, cite_map_path: Path | None = None,
          refs_path: Path | None = None, verbose: bool = True) -> dict:
    cite_map_path = cite_map_path or md_path.parent / "cite_map.json"
    refs_path = refs_path or md_path.parent / "references.md"
    cite_map = json.loads(cite_map_path.read_text(encoding="utf-8")) if cite_map_path.is_file() else {}
    ref_texts = load_references(refs_path) if refs_path.is_file() else {}

    paper = parse_markdown(md_path.read_text(encoding="utf-8"))
    plan, notes, abstract_blocks = plan_document(paper)

    b = Builder(template, md_path, cite_map, ref_texts)
    # number citations in output order: abstract first, then the planned body
    for t in _all_text(abstract_blocks):
        b.citer.register_text(t)
    for kind, payload in plan:
        if kind in ("blocks", "blocks_h3"):
            for t in _all_text(payload):
                b.citer.register_text(t)

    b.clear_body_after_title()
    b.fill_title_block(paper.title, author_line(paper.front), abstract_blocks)
    for kind, payload in plan:
        if kind == "h2":
            b.h2(payload)
        elif kind == "h3":
            b.h3(payload)
        elif kind == "blocks":
            b.blocks(payload)
        elif kind == "blocks_h3":
            b.blocks(payload, in_h3=True)
        elif kind == "todo":
            b.placeholder(payload)
        elif kind == "references":
            b.references()
        elif kind == "count_on":
            b.counting = True
        elif kind == "count_off":
            b.counting = False

    cp = b.doc.core_properties
    cp.title = paper.title
    author = author_line(paper.front).split(", ")[0]
    cp.author = author
    cp.last_modified_by = author
    cp.comments = ""
    cp.keywords = ""
    out.parent.mkdir(parents=True, exist_ok=True)
    b.doc.save(str(out))

    pages = b.words / 500 + b.figs_in_body * 0.4
    stats = {"out": str(out), "words_main": b.words, "figures_main": b.figs_in_body,
             "figures_total": b.fig_no, "pages_est": pages, "citations": len(b.citer.order),
             "missing_figures": b.missing_figs, "notes": notes + b.warnings}
    if verbose:
        print(f"wrote {out}")
        print(f"citations: {len(b.citer.order)} references numbered in first-citation order")
        if b.missing_figs:
            print("missing figures: " + ", ".join(b.missing_figs))
        for n in notes + b.warnings:
            print(f"note: {n}")
        print(f"main body (sections 1-6): {b.words} words, {b.figs_in_body} figures "
              f"-> ~{pages:.1f} pages (words/500 + figures*0.4)")
        if pages > 8:
            print(f"WARNING: main body estimate {pages:.1f} pages exceeds 8 pages")
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--md", type=Path, default=HERE / "paper.md")
    ap.add_argument("--template", type=Path, default=HERE / "template.docx")
    ap.add_argument("--out", type=Path, default=HERE / "SwarmImmunity_report.docx")
    ap.add_argument("--cite-map", type=Path, default=None, help="default: <md dir>/cite_map.json")
    ap.add_argument("--references", type=Path, default=None, help="default: <md dir>/references.md")
    args = ap.parse_args(argv)
    build(args.md, args.template, args.out, args.cite_map, args.references)
    return 0


if __name__ == "__main__":
    sys.exit(main())

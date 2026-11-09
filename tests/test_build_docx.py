"""Tests for paper/build_docx.py (synthetic markdown + the real Apart template)."""
import importlib.util
import json
import sys
from pathlib import Path

import docx
import pytest
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper"
TEMPLATE = PAPER / "template.docx"

spec = importlib.util.spec_from_file_location("build_docx", PAPER / "build_docx.py")
bd = importlib.util.module_from_spec(spec)
sys.modules["build_docx"] = bd
spec.loader.exec_module(bd)

pytestmark = pytest.mark.skipif(not TEMPLATE.is_file(), reason="template.docx missing")

EXPECTED_H2 = ["1. Introduction", "2. Related Work", "3. Methods", "4. Results",
               "5. Discussion and Limitations", "6. Conclusion", "Code and Data", "References",
               "Appendix", "LLM Usage Statement"]
GUIDANCE = ["How to use this template", "What problem are you addressing", "Recommended length",
            "PROJECT TITLE", "Author name", "Summarize your project", "[Reference 1]",
            "Briefly summarize your main findings", "If you used LLM assistance"]

SYNTH_MD = r"""# A Tiny Test Paper

**Ada Lovelace**, Analytical Engine Institute (AEI) London

> **Draft status.** Not part of the report.

## Abstract

*(150–250 words, written last.)*

We study swarms [X1] with a fraction $f\in[0,1]$ of attackers.

## 1. Introduction

Swarms coordinate [X2, X3, X4] and [X5–X6, X2]. Not citations: [TBD], [4,16], [Q9].
Math: $Q_o=\sum_a w_a v_{o,a}$ and $o^\star=\arg\max_o Q_o$, $\frac{a}{b}$, $\overline{b}_{\mathcal N(i)}$.

1. First **bold** item with `code`
   - nested bullet
2. Second item

| ID | Rule |
|---|---|
| M1 | down-weight by $(1-\rho)^s$ [X1] |

![An overview](fig.png){width=3.2in}

[FIGURE: nope/missing.png | A missing figure]

## 2. Related work

Prior work [X7].

## 3. Methods

### 3.1 Task

Text with $\kappa$ and $\lambda$.

#### A bold paragraph heading

Body.

## 4. Results

[TBD]

## 5. Discussion

Discussion text.

## 6. Limitations and future work

- **Small.** Only N=12.

## 7. Conclusion

We conclude.

## Appendix A. Dual-use and ethical considerations

Benign task.

## Appendix B. Deviations

See [DEVIATIONS.md](../DEVIATIONS.md).

## References

Old note [X1].
"""


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    from PIL import Image

    d = tmp_path_factory.mktemp("paper")
    (d / "paper.md").write_text(SYNTH_MD, encoding="utf-8")
    Image.new("RGB", (40, 20), "white").save(d / "fig.png")
    cite_map = {f"X{i}": {"number": 10 + i, "short": f"Ref{i}", "url": f"https://x/{i}"} for i in range(1, 9)}
    (d / "cite_map.json").write_text(json.dumps(cite_map), encoding="utf-8")
    refs = "\n".join(f"{10 + i}. Author{i}. (2020). *Title {i}*. https://x/{i}" for i in range(1, 9))
    (d / "references.md").write_text("# References\n\n" + refs + "\n", encoding="utf-8")
    out = d / "out.docx"
    stats = bd.build(d / "paper.md", TEMPLATE, out, verbose=False)
    return docx.Document(str(out)), stats


def _all_paragraphs(doc):
    return [Paragraph(p, doc._body) for p in doc.element.body.iter(qn("w:p"))]


def _all_text(doc):
    return "\n".join(p.text for p in _all_paragraphs(doc))


def _h2(doc):
    return [p.text.strip() for p in doc.paragraphs if p.style.name == "Heading 2"]


def test_heading_order(synth):
    doc, _ = synth
    assert _h2(doc) == EXPECTED_H2
    h3 = [p.text for p in doc.paragraphs if p.style.name == "Heading 3"]
    assert h3 == ["3.1 Task", "Limitations", "Future Work", bd.LIMITATIONS_APPENDIX_HEADING, "Deviations"]


def test_no_guidance_or_raw_markup(synth):
    doc, _ = synth
    text = _all_text(doc)
    for g in GUIDANCE:
        assert g not in text, g
    assert "\\" not in text
    assert "$" not in text
    assert "**" not in text
    assert "Draft status" not in text
    assert "written last" not in text
    assert len(doc.tables) == 2  # title block + one content table (guidance box removed)


def test_title_author_abstract(synth):
    doc, _ = synth
    tblt = "\n".join(Paragraph(p, None).text for p in doc.tables[0]._tbl.iter(qn("w:p")))
    assert "A Tiny Test Paper" in tblt
    assert "Ada Lovelace, AEI London" in tblt
    assert "We study swarms [1]" in tblt


def test_citations_numbered_and_compressed(synth):
    doc, stats = synth
    text = _all_text(doc)
    assert "Swarms coordinate [2–4] and [2, 5, 6]" in text
    assert "[TBD], [4,16], [Q9]" in text
    assert "Prior work [7]" in text
    # references: only cited ones (X8 never cited), numbered in first-citation order
    refs = [p.text for p in doc.paragraphs if p.text.startswith("[") and "\t" in p.text]
    assert [r.split("\t")[0] for r in refs] == [f"[{i}]" for i in range(1, 8)]
    assert refs[0].endswith("https://x/1") and "Author1" in refs[0]
    assert not any("Author8" in r for r in refs)
    assert stats["citations"] == 7


def test_math_converted(synth):
    doc, _ = synth
    text = _all_text(doc).replace("\u00a0", " ")   # inline math uses non-breaking spaces
    assert "Qo = Σawavo,a" in text
    assert "o* = argmaxoQo" in text
    assert "a/b" in text
    assert "b̄𝒩(i)" in text
    assert "κ" in text and "λ" in text
    sub = [r for p in doc.paragraphs for r in p.runs if r.font.subscript]
    assert sub, "expected subscript runs"


def test_lists_table_figures(synth):
    doc, stats = synth
    numbered = [p for p in doc.paragraphs if p._p.find(".//" + qn("w:numPr")) is not None]
    texts = [p.text for p in numbered]
    assert "First bold item with code" in texts and "nested bullet" in texts
    lvl = {p.text: p._p.find(".//" + qn("w:ilvl")).get(qn("w:val")) for p in numbered}
    assert lvl["nested bullet"] == "1"
    code_runs = [r for p in numbered for r in p.runs if r.text == "code"]
    assert code_runs[0]._r.find(".//" + qn("w:rFonts")).get(qn("w:ascii")) == bd.CODE_FONT
    t = doc.tables[1]
    assert [c.text for c in t.rows[0].cells] == ["ID", "Rule"]
    assert all(r.bold for r in t.rows[0].cells[0].paragraphs[0].runs)
    assert "[1]" in t.rows[1].cells[1].text
    assert len(doc.inline_shapes) == 1
    assert abs(doc.inline_shapes[0].width.inches - 3.2) < 0.01
    text = _all_text(doc)
    assert "Figure 1. An overview" in text
    assert "[missing figure: nope/missing.png]" in text and "Figure 2. A missing figure" in text
    assert stats["missing_figures"] == ["nope/missing.png"]


def test_section_mapping(synth):
    doc, _ = synth
    text = _all_text(doc)
    assert "We conclude." in text and "TODO: Conclusion" not in text
    assert "TODO: Future work" in text
    assert "[Author to write]" in text
    assert "Old note" not in text
    assert bd.REPO_URL in text
    assert "replay byte-for-byte" in text
    # limitations appear both in the main body and in the required appendix section
    assert text.count("Small. Only N=12.") == 1
    paras = [p.text for p in doc.paragraphs]
    i = paras.index(bd.LIMITATIONS_APPENDIX_HEADING)
    assert "Benign task." in paras[i + 1]
    assert "A bold paragraph heading" in paras


def test_unit_helpers():
    assert bd.compress_numbers([9, 3, 4, 5]) == "3–5, 9"
    assert bd.compress_numbers([1, 2]) == "1, 2"
    cm = {"G2": {}, "G3": {}, "G4": {}, "C7": {}}
    assert bd.expand_cite("G2–G4", cm) == ["G2", "G3", "G4"]
    assert bd.expand_cite("C7, G2", cm) == ["C7", "G2"]
    assert bd.expand_cite("TBD", cm) is None
    assert bd.expand_cite("0,1", cm) is None
    for src in [r"\mathbb 1[c_i^{(R-1)}=o^\star]", r"\frac1{|\mathcal H|}\sum_{i\in\mathcal H}x",
                r"\le0.15", r"\big(1+e^{-(f-f^\star)/s}\big)^{-1}", r"\unknowncmd{x}\$"]:
        out = bd.tex_to_text(src)
        assert "\\" not in out and "$" not in out, out
    assert bd.tex_to_text(r"\mathbb 1") == "𝟙"
    assert bd.tex_to_text(r"\overline{b}") == "b̄"
    assert bd.tex_to_text(r"x \le y") == "x ≤ y"


@pytest.mark.skipif(not (PAPER / "paper.md").is_file(), reason="paper.md missing")
def test_real_paper(tmp_path):
    out = tmp_path / "real.docx"
    stats = bd.build(PAPER / "paper.md", TEMPLATE, out, verbose=False)
    doc = docx.Document(str(out))
    assert _h2(doc) == EXPECTED_H2
    text = _all_text(doc)
    assert "\\" not in text and "$" not in text
    for g in GUIDANCE:
        assert g not in text, g
    assert stats["pages_est"] > 0

"""Parity tests for PDF rendering (roboviva/tex.py -> pdflatex).

PDFs are not byte-reproducible -- /ID and /CreationDate change every run -- so
the asserted artifact is a structural summary: page count, page geometry, and
the normalized text layer. The .tex source remains the byte-exact contract
(test_latex_document.py); this tier catches the things LaTeX decides for
itself, including whether it produces a file at all.

Extraction uses the same pypdf version on both sides of the comparison, so the
extractor can never be the source of a difference.
"""
import pytest

from conftest import assert_matches, load_corpus, load_golden


def _by_name():
    return {g["name"]: g for g in load_golden("pdf/documents.json")}


def _pdf(name):
    g = _by_name()[name]
    assert g["ok"], "render stage failed: %s" % g.get("error")
    return g["result"]


def _cases():
    idx = _by_name()
    out = []
    for c in load_corpus("latex/documents.json"):
        if c["name"] in idx:
            out.append(pytest.param(c, idx[c["name"]], id=c["name"]))
    return out


@pytest.mark.parametrize("case,expected", _cases())
def test_pdf_summary_matches_golden(sut, case, expected):
    """Render each document and compare the structural summary."""
    if not expected["ok"]:
        # The document failed before pdflatex was reached (e.g. a string id).
        with pytest.raises(Exception):
            sut.render_pdf(sut.make_latex(case["route"]))
        return
    latex_src = sut.make_latex(case["route"])
    assert sut.render_pdf(latex_src) == expected["result"], (
        "PDF summary differs for %r\n  why: %s" % (case["name"], case["why"]))


def test_pages_are_us_letter():
    """612x792pt from \\geometry{letterpaper} (latex.py:170).

    A cue sheet is printed and folded into a handlebar bag, so paper size is a
    real product decision rather than an incidental default.
    """
    page = _pdf("minimal")["pages"][0]
    assert (page["width_pt"], page["height_pt"]) == (612, 792)


def test_long_route_paginates():
    """120 cues spill onto a second page via supertabular.

    supertabular is what makes this work without manual page breaks, and it is
    also why \\pageref{LastPage} needs two pdflatex passes to settle.
    """
    assert _pdf("multipage")["page_count"] == 2


def test_rendered_text_contains_the_cue_data():
    """The text layer carries the actual cue content, not just chrome."""
    text = _pdf("named_route")["pages"][0]["text"]
    assert "Test Route" in text
    assert "Foo St." in text
    for column in ("Go", "At", "On", "For"):
        assert column in text


def test_caret_in_a_description_produces_no_pdf_at_all():
    """BUG: one unescaped '^' anywhere destroys the whole cue sheet.

    _escape (latex.py:48-63) handles # & $ _ | < > % { } and U+200B but not
    '^'. LaTeX reads a bare caret as the superscript operator outside math
    mode, raises "Missing $ inserted", and -halt-on-error means NO output file
    is produced -- not a garbled cell, no PDF.

    Through the web layer this surfaces as "Guru Meditation: 0xFF" with no
    indication of which cue caused it. See test_approval_routes.py for a real
    public route this actually breaks.
    """
    result = _pdf("caret_in_description")
    assert result["rendered"] is False
    assert any("Missing $ inserted" in line
               for line in result["error_excerpt"]), result["error_excerpt"]


def test_tilde_renders_but_is_silently_wrong():
    """'~' is also unescaped, but it is valid LaTeX -- a non-breaking space.

    So it degrades quietly instead of failing loudly: the character the rider
    typed simply is not in the output.
    """
    result = _pdf("tilde_in_description")
    assert result["rendered"] is True
    assert "~" not in result["pages"][0]["text"], (
        "the tilde is consumed as a non-breaking space, not printed")


@pytest.mark.parametrize("name,char", [
    ("unicode_greek_name", "Φ"),
    ("unicode_cjk", "タ"),
])
def test_non_latin_text_cannot_be_rendered(name, char):
    """Greek and CJK are fatal: inputenc has no mapping for them.

    pdflatex with the fourier/helvet 8-bit font stack simply has no glyph, and
    inputenc raises rather than dropping the character. Any RideWithGPS route
    with a non-Latin name or description is unrenderable -- and there are
    plenty of public ones.

    This is a hard limitation of the LaTeX backend, not a bug in roboviva's
    own code. A rewrite on a Unicode-capable engine (XeLaTeX, or ReportLab as
    the python3 branch uses) would fix it for free, which makes it a good
    argument for the rewrite rather than something to preserve.
    """
    result = _pdf(name)
    assert result["rendered"] is False
    assert any("inputenc" in line and char in line
               for line in result["error_excerpt"]), result["error_excerpt"]


def test_accented_latin_does_render():
    """Latin-1 accents are fine -- the limit is the 8-bit encoding, not accents."""
    result = _pdf("unicode_latin")
    assert result["rendered"] is True
    assert "glise" in result["pages"][0]["text"], (
        "expected 'Rue de l'Église' to survive into the text layer")


def test_all_instruction_glyphs_render():
    """Every Instruction value produces output, including the symbol ones.

    Covers \\Mountain (ifsym), \\danger (fourier) and \\Plus (bbding), which
    are the reason the image needs texlive-fonts-extra at all.
    """
    result = _pdf("all_instruction_glyphs")
    assert result["rendered"] is True
    assert result["page_count"] == 1


def test_empty_route_still_produces_a_pdf():
    """A cue sheet with no cues is a valid, if useless, one-page document."""
    result = _pdf("empty_route")
    assert result["rendered"] is True
    assert result["page_count"] == 1

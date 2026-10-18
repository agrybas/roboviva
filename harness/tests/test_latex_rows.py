"""Parity tests for a single supertabular row (latex._entryToLatex).

One cue entry becomes one table row with four columns -- Go, At, On, For --
built by %-formatting at latex.py:132-137. The column widths and the exact
spacing are part of the contract because they are what a rider reads.

The escape-then-format order matters and is a security boundary: _escape runs
first so user text cannot inject LaTeX, and _format runs second so the
markdown-ish emphasis it introduces is trusted output rather than input.
"""
import pytest

from conftest import assert_matches, load_golden, paired


def _row(name):
    for g in load_golden("latex/entry_rows.json"):
        if g["name"] == name:
            assert g["ok"], g
            return g["result"]
    raise AssertionError("no golden named %r" % name)


@pytest.mark.parametrize("case,expected", paired("latex/entry_rows.json"))
def test_entry_to_latex_row(sut, case, expected):
    """Byte-exact row parity for every entry shape in the corpus."""
    assert_matches(lambda: sut.entry_to_latex_row(case["entry"]),
                   expected, case)


def test_note_is_appended_as_italic_newline():
    """A note becomes ' \\newline \\textit{...}' (latex.py:125).

    The in-repo latex_tests.py:139 still expects '\\textbf{Note:} \\emph{...}',
    which the code stopped producing in commit 69ee4d1. The golden here reflects
    the code, not that test.
    """
    row = _row("with_note")
    assert r"\newline \textit{watch for gravel}" in row
    assert "Note:" not in row, "the 'Note:' label was removed in 69ee4d1"


def test_note_replaces_a_blank_description():
    """With no description, the note fills the On column outright.

    latex.py:121-123. Without this a note-only cue -- "regroup here", with no
    turn -- would render an empty On column.
    """
    row = _row("note_without_description")
    assert "Regroup here" in row
    assert r"\newline" not in row, "promoted, not appended"


def test_whitespace_description_also_promotes_the_note():
    """The blank check is .strip(), so a spaces-only description counts."""
    assert r"\newline" not in _row("whitespace_only_description")


def test_zero_for_distance_renders_as_empty():
    """A for_distance of exactly 0.0 leaves the For column blank.

    `if entry.for_distance:` (latex.py:126) is a truthiness test, so a genuine
    zero-length leg is indistinguishable from a missing one -- the same quirk
    Entry.__repr__ has.
    """
    row = _row("for_distance_zero")
    assert row.endswith(r"&  \\ \hline"), row


def test_small_for_distance_still_renders():
    """0.04mi is truthy, so it prints -- rounded to 0.0 by %5.1f.

    So the For column can legitimately show "0.0" for a short leg while a true
    zero shows nothing at all.
    """
    assert "0.0" in _row("for_distance_rounding")


def test_row_colours():
    """\\rowcolor arguments in context (latex.py:98-101, 117)."""
    assert _row("yellow_row").startswith(r"\rowcolor{yellow}")
    assert _row("gray_row").startswith(r"\rowcolor[gray]{0.8}")
    assert _row("minimal").startswith(" "), "no colour -> no \\rowcolor prefix"


def test_modifiers_concatenate_onto_the_instruction():
    """Modifier and instruction are simply concatenated (latex.py:46)."""
    assert r"\textbf{QR}" in _row("modifier_quick")
    assert r"\textbf{BL}" in _row("modifier_slight")


def test_climb_and_symbol_glyphs():
    """Climb categories, summit and first aid are symbols, not letters."""
    assert r"\Mountain" in _row("climb_glyph")
    assert r"\Mountain" in _row("summit_glyph")
    assert r"\textbf{End}" in _row("summit_glyph"), "summit is labelled 'End'"
    assert r"\Plus" in _row("first_aid_glyph")


def test_user_text_cannot_inject_latex():
    """Every LaTeX special in a description is neutralized.

    Descriptions come from RideWithGPS, which anyone can edit, and are compiled
    by pdflatex. This is the boundary that stops a cue sheet from running
    arbitrary TeX.
    """
    row = _row("escaping_in_description")
    assert r"\textbackslash cmd" in row, "backslash neutralized"
    assert r"\&" in row and r"\%" in row and r"\#" in row
    # A bare & would end the column early; a bare % would comment the row out.
    assert row.count("&") == row.count(r"\&") + 3, (
        "exactly three unescaped column separators expected: %r" % row)


def test_ampersand_and_percent_are_escaped_in_real_street_names():
    """The two that would actually corrupt the table, in realistic text."""
    assert r"Smith \& Wesson Ave" in _row("ampersand_would_break_the_table")
    assert r"50\% grade" in _row("percent_would_comment_the_row")


def test_custom_instruction_is_escaped_too():
    """The [tag] is user input and reaches the Go column (latex.py:46)."""
    assert r"\textbf{R\&D}" in _row("custom_instruction_with_specials")


def test_emphasis_survives_escaping():
    """**bold** and *italic* become real LaTeX in descriptions and notes."""
    assert r"\textbf{big}" in _row("emphasis_in_description")
    assert r"\emph{barn}" in _row("emphasis_in_description")
    assert r"\textbf{Do not}" in _row("emphasis_in_note")


def test_zero_width_space_becomes_zero_width_hspace():
    """U+200B -> \\hspace{0pt} (latex.py:62, commit 2278d0d).

    RideWithGPS joins concatenated street names with a zero-width space.
    pdflatex cannot typeset the character itself, so it is translated into a
    LaTeX construct that preserves the (zero) width and the line-break
    opportunity.
    """
    row = _row("zwsp_in_description")
    assert r"\hspace{0pt}" in row
    assert "​" not in row, "the raw character must not survive"


def test_unmapped_instruction_renders_as_literal_text():
    """Route 55132669's 'Uturn' becomes a bold word in the Go column."""
    assert r"\textbf{Uturn}" in _row("unmapped_uturn")

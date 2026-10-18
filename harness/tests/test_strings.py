"""Parity tests for the pure string functions.

These are the functions a rewrite is most likely to "clean up" without
noticing: LaTeX escaping, the markdown-ish emphasis parser, and the ordered
regex substitutions that normalize RideWithGPS description strings. Every case
here is pinned to observed legacy output, not to the repo's own (stale) tests.
"""
import pytest

from conftest import assert_matches, paired


@pytest.mark.parametrize("case,expected", paired("strings/escape.json"))
def test_escape(sut, case, expected):
    """latex._escape -- LaTeX special-character escaping (latex.py:48-63).

    Also the service's injection boundary: users control descriptions, notes
    and custom instruction tags via RideWithGPS, and this is the only thing
    standing between that text and a LaTeX compiler.
    """
    assert_matches(lambda: sut.escape(case["text"]), expected, case)


@pytest.mark.parametrize("case,expected", paired("strings/format.json"))
def test_format_markup(sut, case, expected):
    """latex._format -- *emph* / **strong** (latex.py:65-90).

    Runs AFTER _escape, so it sees text that already contains \\textbackslash
    and friends. The two-pass regex approach has well-defined but unobvious
    behavior on unbalanced delimiters, which is exactly what these cases pin.
    """
    assert_matches(lambda: sut.format_markup(case["text"]), expected, case)


@pytest.mark.parametrize("case,expected",
                         paired("strings/clean_description.json"))
def test_clean_description(sut, case, expected):
    """ridewithgps._cleanDescription -- ten ordered re.sub calls (:252-261).

    Strips the redundant turn verb RideWithGPS puts in every description, so
    the "On" column reads "Foo St." rather than "Turn right onto Foo St.".
    Rule order matters and is part of the contract.
    """
    assert_matches(lambda: sut.clean_description(case["description"]),
                   expected, case)


@pytest.mark.parametrize("case,expected",
                         paired("strings/parse_custom_instruction.json"))
def test_parse_custom_instruction(sut, case, expected):
    """ridewithgps._parseCustomInstruction -- the [tag] extension (:346-371).

    RideWithGPS is the only editing UI, so the user's only way to override an
    instruction is a bracketed prefix inside the description text.
    """
    assert_matches(lambda: sut.parse_custom_instruction(case["description"]),
                   expected, case)


@pytest.mark.parametrize("case,expected",
                         paired("strings/instruction_str_to_cue.json"))
def test_instruction_str_to_cue(sut, case, expected):
    """ridewithgps._instructionStrToCueInstruction (:264-296).

    Case-sensitive lookup with a passthrough fallback. Real routes rely on the
    fallback more than you would expect -- 'Uturn', 'Climb', 'Valley' and even
    lowercase 'right'/'left' all appear in public routes today.
    """
    assert_matches(lambda: sut.instruction_str_to_cue(case["instruction_str"]),
                   expected, case)


@pytest.mark.parametrize("case,expected",
                         paired("strings/color_from_instruction.json"))
def test_color_from_instruction(sut, case, expected):
    """cue.ColorFromInstruction -- row colour from instruction (cue.py:47-56).

    Includes the missing-comma substring quirk that makes every Start/End/
    Generic row gray. See the 'none_empty_string' case.
    """
    assert_matches(lambda: sut.color_from_instruction(case["instruction"]),
                   expected, case)


@pytest.mark.parametrize("case,expected",
                         paired("strings/instruction_to_latex.json"))
def test_instruction_to_latex(sut, case, expected):
    """latex._instructionToLatex -- the "Go" column glyph (latex.py:24-46).

    Climb categories and Summit become mountain glyphs, Danger and First Aid
    become symbols, and everything else -- including arbitrary user-supplied
    custom instructions -- is escaped and set bold.
    """
    assert_matches(
        lambda: sut.instruction_to_latex(case["instruction"], case["modifier"]),
        expected, case)


@pytest.mark.parametrize("case,expected", paired("strings/entry_color.json"))
def test_entry_color(sut, case, expected):
    """latex._entryColor -- cue.Color to a \\rowcolor argument (latex.py:92-102)."""
    assert_matches(lambda: sut.entry_color(case["color"]), expected, case)

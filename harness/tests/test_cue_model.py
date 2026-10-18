"""Parity tests for the cue data model (cue.py).

`Entry` and `Route` are plain storage classes, but their `__repr__` is the
closest thing the codebase has to a serialization format -- the CLI prints it
and the error paths log it -- so the exact spacing is part of the contract.

The enum values matter more than they look: cue.Instruction members are plain
strings, so `==`, `in` and substring semantics all apply to them. That is what
makes the ColorFromInstruction quirk possible (see test_strings.py).
"""
import pytest

from conftest import assert_matches, load_golden, paired


@pytest.mark.parametrize("case,expected", paired("model/entry_repr.json"))
def test_entry_repr(sut, case, expected):
    """cue.Entry.__repr__ -- fixed-width formatting (cue.py:85-98).

    Covers float() coercion of absolute_distance and the fact that a
    for_distance of exactly 0.0 is falsy and therefore prints as blank,
    indistinguishable from None.
    """
    assert_matches(lambda: sut.entry_repr(case["entry"]), expected, case)


@pytest.mark.parametrize("case,expected", paired("model/route_repr.json"))
def test_route_repr(sut, case, expected):
    """cue.Route.__repr__ (cue.py:124-133).

    Note the constructor's argument order is (entries, length_mi, route_id,
    ...) -- length before id, which is easy to transpose in a rewrite and
    would silently produce a route whose id is its length.
    """
    assert_matches(lambda: sut.route_repr(case["route"]), expected, case)


def test_instruction_enum_values(sut):
    """The exact string values of cue.Instruction (cue.py:21-35).

    These leak into rendered output: Instruction.LEFT is literally the "L" that
    appears in the Go column, and Instruction.NONE is the empty string that
    makes ColorFromInstruction return GRAY. A rewrite using a real enum.Enum
    must keep the same *values*.
    """
    expected = load_golden("environment.json")["enums"]["Instruction"]
    assert sut.enums()["Instruction"] == expected
    assert expected["NONE"] == "", (
        "Instruction.NONE must stay the empty string -- the gray-row behavior "
        "of every Start/End/Generic entry depends on it")


def test_modifier_enum_values(sut):
    """cue.Modifier values (cue.py:38-40).

    Rendered by concatenation in front of the instruction, so QUICK + RIGHT
    becomes the string "QR" in the Go column.
    """
    expected = load_golden("environment.json")["enums"]["Modifier"]
    assert sut.enums()["Modifier"] == expected
    assert expected == {"NONE": "", "SLIGHT": "B", "QUICK": "Q"}


def test_color_enum_values(sut):
    """cue.Color values (cue.py:43-45).

    Human-readable names rather than LaTeX; the mapping to \\rowcolor happens
    in latex._entryColor.
    """
    expected = load_golden("environment.json")["enums"]["Color"]
    assert sut.enums()["Color"] == expected
    assert expected == {"NONE": "None", "GRAY": "Gray", "YELLOW": "Yellow"}


def test_unreachable_instructions_are_still_defined(sut):
    """CAT_5 and CROSSES exist but nothing can produce them.

    _instructionStrToCueInstruction (ridewithgps.py:264-296) has no RideWithGPS
    string that maps to either one, and no real route uses them. They are
    recorded here so a rewrite that drops them does so knowingly -- they are
    reachable by a user typing [C5] or [X] as a custom instruction tag, which
    renders quite differently from the enum path.
    """
    instructions = sut.enums()["Instruction"]
    assert instructions["CAT_5"] == "C5"
    assert instructions["CROSSES"] == "X"

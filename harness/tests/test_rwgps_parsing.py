"""Parity tests for turning a RideWithGPS payload into a cue.Route.

This is where the domain translation happens, and where a rewrite is most
likely to drift without noticing:

  * RideWithGPS's field names are INVERTED relative to roboviva's. The course
    point's 'n' (which RideWithGPS calls the note) becomes roboviva's
    DESCRIPTION, and 'description' becomes roboviva's NOTE
    (ridewithgps.py:136-141).
  * Two sentinel entries are synthesized that have no counterpart in the
    payload: "Start of route" at distance 0 and "End of route" at the route's
    total length (ridewithgps.py:128-133, :159-164).
  * Modifiers are inferred, not given -- from the description text for SLIGHT
    and from inter-point distance for QUICK.
"""
import pytest

from conftest import assert_matches, load_golden, paired


def _route(name):
    for g in load_golden("rwgps/parse_json.json"):
        if g["name"] == name:
            assert g["ok"] and g["result"]["ok"], g
            return g["result"]["route"]
    raise AssertionError("no golden named %r" % name)


@pytest.mark.parametrize("case,expected", paired("rwgps/parse_json.json"))
def test_parse_json(sut, case, expected):
    """Full parse parity for every payload shape in the corpus."""
    assert_matches(
        lambda: sut.fetch_json(case["route_id"], case.get("etag"),
                               case["script"]),
        expected, case)


def test_start_and_end_sentinels_are_synthesized():
    """A route with zero course points still yields two entries.

    RideWithGPS does not mark the start or the end of a route, so the parser
    invents both. The end sentinel exists specifically so the last real cue has
    a correct "For" distance (ridewithgps.py:156-157).
    """
    entries = _route("no_course_points")["entries"]
    assert len(entries) == 2
    assert entries[0]["description"] == "Start of route"
    assert entries[0]["absolute_distance"] == 0.0
    assert entries[-1]["description"] == "End of route"


def test_rwgps_field_names_are_inverted():
    """'n' -> description, 'description' -> note.

    The single most confusing thing in the codebase. RideWithGPS's UI labels
    the short turn text a "note"; roboviva calls that the description and
    reserves "note" for RideWithGPS's longer "description" field.
    """
    entries = _route("note_present")["entries"]
    cue = entries[1]
    assert cue["description"] == "Foo", "RWGPS 'n' became the description"
    assert cue["note"] == "Bring cash", "RWGPS 'description' became the note"


def test_quick_modifier_from_proximity():
    """Turns within 0.1mi of the previous point are marked QUICK.

    ridewithgps.py:311-315. The threshold is hard-coded; the
    `quick_threshold_mi` parameter in the signature is never consulted.
    """
    entries = _route("quick_turn_cluster")["entries"]
    quick = [e for e in entries if e["modifier"] == "Q"]
    assert len(quick) >= 2, [e["modifier"] for e in entries]


def test_slight_modifier_from_description_text():
    """'Keep|Bear|Slight ' at the start of the description means SLIGHT.

    Inferred from prose because the RideWithGPS type for a gentle turn is just
    "Right" -- the only signal is the wording (ridewithgps.py:307-310).
    """
    entries = _route("slight_turn_by_description")["entries"]
    assert any(e["modifier"] == "B" for e in entries), \
        [e["modifier"] for e in entries]


def test_slight_modifier_is_case_sensitive():
    """Lowercase 'bear right' does NOT get SLIGHT.

    The regex at ridewithgps.py:309 has no re.I, unlike every rule in
    _cleanDescription. Almost certainly unintentional, and it matters: the turn
    silently falls through to the distance-based QUICK check instead.
    """
    entries = _route("slight_case_sensitive")["entries"]
    assert not any(e["modifier"] == "B" for e in entries), \
        "lowercase should not produce SLIGHT"


def test_zero_previous_distance_skips_quick_check():
    """A previous distance of exactly 0.0 disables the QUICK heuristic.

    `elif entry.prev_absolute_distance:` (ridewithgps.py:311) is a truthiness
    test, and 0.0 is falsy. So a turn 50m after the route start -- unambiguously
    quick -- is not marked quick, purely because the start sits at mile 0.
    """
    entries = _route("zero_distance_first_point")["entries"]
    assert entries[1]["modifier"] == "", (
        "expected the QUICK check to be skipped at distance 0")


def test_custom_tag_overrides_instruction_but_not_colour():
    """A [tag] replaces the instruction and clears the modifier -- colour stays.

    ridewithgps.py:380-388 computes the colour from the RideWithGPS type BEFORE
    applying the custom tag, and never recomputes it. So a [U] tag on a Danger
    point keeps its yellow row while showing "U" in the Go column. Probably
    intentional -- the hazard is still a hazard -- but it is not written down
    anywhere, so it is pinned here.
    """
    entries = _route("custom_instruction_tag")["entries"]
    tagged = [e for e in entries if e["instruction"] == "U"]
    assert tagged, [e["instruction"] for e in entries]
    assert tagged[0]["color"] == "Yellow", "colour survives the override"
    assert tagged[0]["modifier"] == "", "modifier is cleared"
    assert tagged[0]["description"] == "Sharp bend", "the tag is stripped"


def test_start_tag_replaces_the_synthesized_start():
    """[start] promotes a real cue into the first row (ridewithgps.py:174)."""
    entries = _route("start_tag_promotes_entry")["entries"]
    assert entries[0]["description"] == "Real start"
    assert entries[0]["absolute_distance"] == 0.0
    assert entries[0]["instruction"] == "", "reset to Instruction.NONE"


def test_unmapped_types_pass_through_as_literal_text():
    """Uturn / Climb / Valley / lowercase right and left reach the Go column raw.

    All five appear in public routes today. They render as bold literal words
    rather than symbols, and -- because they are not Instruction.RIGHT -- the
    lowercase 'right' also loses the gray row shading a real right turn gets.
    """
    entries = _route("unmapped_instruction_types")["entries"]
    instructions = [e["instruction"] for e in entries]
    for expected in ("Uturn", "Climb", "Valley", "right", "left"):
        assert expected in instructions, instructions
    lowercase_right = next(e for e in entries if e["instruction"] == "right")
    assert lowercase_right["color"] == "None", (
        "a lowercase 'right' does not get the gray shading of a real R")


def test_unit_conversions():
    """Meters to miles and feet (ridewithgps.py:124-125).

    Exactly one mile and exactly 1000 feet in, so a wrong constant is obvious.
    """
    route = _route("unit_conversion")
    assert route["length_mi"] == pytest.approx(1.0, abs=1e-6)
    assert route["elevation_gain_ft"] == pytest.approx(1000.0, abs=0.5)


def test_zero_elevation_gain_is_preserved_as_zero():
    """0 climb stays 0 here; the header drops it later because 0 is falsy."""
    assert _route("zero_elevation_gain")["elevation_gain_ft"] == 0.0


def test_missing_optional_fields_become_empty_strings():
    """Absent 'n' and 'description' become '', never None.

    Downstream, latex._entryToLatex tests `if entry.note:` and
    `esc_description.strip()`, both of which would break on None.
    """
    no_n = _route("missing_n_field")["entries"][1]
    assert no_n["description"] == ""
    no_desc = _route("missing_description_field")["entries"][1]
    assert no_desc["note"] == ""

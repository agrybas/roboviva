"""Parity tests for cue_utils.AdjustStartAndEnd (cue_utils.py:19-49).

The feature: a rider tags a cue entry with [start] or [end] in RideWithGPS, and
that entry replaces the auto-generated "Start of route"/"End of route" row
rather than sitting alongside it. Shipped in commit 84291c3 and, notably, never
mentioned in tips.html.

The implementation deletes from the list it is iterating over with
`del route.entries[index]` inside an `enumerate` loop, so behavior on anything
beyond the simple single-tag case is emergent. These tests freeze what it
actually does, including two outcomes that are plainly bugs -- recorded so the
rewrite fixes them deliberately rather than inheriting them.
"""
import pytest

from conftest import assert_matches, load_golden, paired


@pytest.mark.parametrize("case,expected", paired("model/adjust_start_end.json"))
def test_adjust_start_and_end(sut, case, expected):
    """Full-route parity for every tagging arrangement in the corpus."""
    assert_matches(lambda: sut.adjust_start_and_end(case["route"]),
                   expected, case)


def _golden(name):
    for g in load_golden("model/adjust_start_end.json"):
        if g["name"] == name:
            return g
    raise AssertionError("no golden named %r" % name)


def test_start_tag_on_last_entry_raises_indexerror():
    """A [start] tag on the final entry crashes.

    The 'end' branch is guarded by `index != len(entries) - 1`
    (cue_utils.py:37) but the 'start' branch has no such guard and reads
    `entries[index + 1]` at cue_utils.py:34.

    In the service this surfaces as the 0xBA "Cue Parsing Failed" error page,
    because handle_request wraps makeLatex -- except the exception actually
    fires earlier, inside getETagAndCuesheet_viaJSON, so it lands in the
    generic handler and renders 0xFA instead. Either way the rider sees a
    failure page for a cue sheet that is merely tagged oddly.
    """
    g = _golden("start_at_last_index")
    assert not g["ok"], "expected this to raise"
    assert g["error"]["type"] == "IndexError"


def test_end_tag_on_last_entry_is_silently_ignored():
    """A [end] tag on the final entry does nothing at all.

    The guard at cue_utils.py:37 skips the branch, so the entry keeps its raw
    'end' instruction string instead of being reset to Instruction.NONE. It
    then flows into the renderer and prints as a literal bold "end" in the Go
    column -- the tag leaks into the output.
    """
    g = _golden("end_at_last_index")
    assert g["ok"]
    last = g["result"]["entries"][-1]
    assert last["instruction"] == "end", (
        "the tag is expected to survive unprocessed; if this changes, the "
        "guard at cue_utils.py:37 was altered")
    assert last["description"] == "foo"


def test_two_start_tags_silently_drop_an_entry():
    """BUG, frozen: a second [start] tag destroys the first one's entry.

    Six entries go in and four come out. 'First start' is gone entirely -- not
    relocated, deleted -- because the loop keeps iterating over a list it has
    already shortened. A rider who tags two entries silently loses cues.
    """
    g = _golden("two_start_tags")
    assert g["ok"]
    entries = g["result"]["entries"]
    assert len(entries) == 4, "six entries in, four out"
    descriptions = [e["description"] for e in entries]
    assert "First start" not in descriptions, "the first tagged entry is lost"
    assert entries[0]["description"] == "Second start"


def test_start_tag_on_first_entry_produces_a_negative_distance():
    """BUG, frozen: tagging entry 0 corrupts the final leg length.

    With index == 0, `entries[index - 1]` is `entries[-1]` -- the LAST entry --
    so the "fix up my predecessor" step at cue_utils.py:32-33 rewrites the end
    of the route using the start of it, yielding for_distance = -7.0.

    A negative for_distance is falsy-safe by luck (it still formats), so this
    reaches the PDF as a nonsense "For" column value rather than crashing.
    """
    g = _golden("start_at_index_0")
    assert g["ok"]
    assert g["result"]["entries"][-1]["for_distance"] == -7.0


def test_empty_route_is_a_safe_noop():
    """Zero entries: the loop body never executes.

    Reachable in practice -- route 5011296 has no course points at all, though
    the JSON path synthesizes Start/End sentinels before this runs.
    """
    g = _golden("empty_route")
    assert g["ok"]
    assert g["result"]["entries"] == []


def test_untagged_route_is_untouched(sut):
    """The overwhelmingly common case: no tags, nothing changes.

    Worth an explicit test because the function mutates in place and returns
    None, so a rewrite that returns a new object must still leave an untagged
    route byte-identical.
    """
    case = next(c for c in
                __import__("conftest").load_corpus("model/adjust_start_end.json")
                if c["name"] == "no_tags")
    result = sut.adjust_start_and_end(case["route"])
    assert result["entries"] == case["route"]["entries"]

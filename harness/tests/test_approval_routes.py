"""End-to-end approval tests over eleven real RideWithGPS routes.

Each route was fetched once from the live API and committed verbatim under
harness/corpus/approval/ (minus route.track_points, the GPS polyline the parser
never reads). Nothing here touches the network; the `-m live` canary is what
notices if a route is later edited or made private.

The chain under test is the whole product:

    recorded payload -> cue.Route -> LaTeX document -> PDF

This is the "does a real cue sheet still come out identical" tier. If the unit
tiers are green and this one is red, the rewrite has changed how the parts
compose rather than how any single part behaves.
"""
import json
import os

import pytest

from conftest import CORPUS, load_golden, load_golden_text


def _index():
    return {g["name"]: g for g in load_golden("approval/index.json")}


def _fixture(route_id, slug):
    path = os.path.join(CORPUS, "approval", "%s-%d.json" % (slug, route_id))
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _cases():
    return [pytest.param(g, id=name) for name, g in sorted(_index().items())]


@pytest.mark.parametrize("expected", _cases())
def test_approval_route_end_to_end(sut, expected):
    """Fetch, parse and render each real route; compare against the golden."""
    fx = _fixture(expected["route_id"], expected["name"])
    script = [{"status": 200,
               "headers": {"ETag": fx["response"]["etag"]},
               "body": fx["response"]["body"]}]

    fetched = sut.fetch_json(expected["route_id"], None, script)
    assert fetched["ok"], "parse failed: %s" % fetched.get("error")
    route = fetched["route"]

    assert len(route["entries"]) == expected["entry_count"]
    assert route["name"] == expected["route_name"]
    assert route["length_mi"] == pytest.approx(expected["length_mi"], rel=1e-9)

    actual_tex = sut.make_latex(route)
    assert actual_tex == load_golden_text(expected["tex"]), (
        "LaTeX differs for route %s (%s)" % (expected["route_id"],
                                             expected["route_name"]))

    assert sut.render_pdf(actual_tex) == expected["pdf"], (
        "PDF summary differs for route %s" % expected["route_id"])


def test_production_routes_render():
    """The four NYCC "AC" club routes are the actual workload.

    These are what Roboviva exists to produce, and all four render cleanly.
    If any of them ever fails, the rewrite has broken the core use case.
    """
    idx = _index()
    for name in ("ac1-westwood", "ac2-ridgewood", "wild-things",
                 "ac12-gunks-and-roses"):
        entry = idx[name]
        assert entry["ok"], entry
        assert entry["pdf"]["rendered"] is True, name
        assert entry["pdf"]["page_count"] >= 1


def test_zero_width_space_routes_render():
    """Three production routes contain U+200B and all render.

    RideWithGPS joins concatenated street names with a zero-width space
    ("Philips Pkwy/<ZWSP>Van Riper Rd"). Before commit 2278d0d that character
    reached pdflatex raw and broke the render; latex.py:62 now maps it to
    \\hspace{0pt}. These routes are the regression test for that fix.
    """
    idx = _index()
    for name in ("ac2-ridgewood", "wild-things"):
        assert idx[name]["pdf"]["rendered"] is True, name


def test_richest_route_covers_the_instruction_variety():
    """Route 55132669 exercises glyphs, colours and unmapped types together.

    Summit x3 (mountain glyph), Danger x3 plus Food/Water (coloured rows), and
    three types the mapping does not know -- Climb, Uturn, Valley -- which fall
    through to literal bold text.
    """
    entry = _index()["ac12-gunks-and-roses"]
    assert entry["pdf"]["rendered"] is True
    text = " ".join(p["text"] for p in entry["pdf"]["pages"])
    for unmapped in ("Uturn", "Climb", "Valley"):
        assert unmapped in text, (
            "%r should appear as literal text in the Go column" % unmapped)


def test_lowercase_instruction_types_reach_the_page():
    """Route 56819245 emits lowercase 'right'/'left' course-point types.

    The mapping is case-sensitive, so these are not Instruction.RIGHT. They
    print as the literal words "right" and "left" in the Go column, next to
    proper "R" and "L" rows -- visibly inconsistent on a real cue sheet.
    """
    entry = _index()["effin-200"]
    assert entry["pdf"]["rendered"] is True
    text = " ".join(p["text"] for p in entry["pdf"]["pages"])
    assert "right" in text or "left" in text


def test_route_with_no_course_points_still_renders():
    """Route 5011296 has zero course points but 123 miles of track.

    The sheet is just the two synthesized sentinels -- useless to ride from,
    but it renders rather than failing, which is the behavior to preserve.
    """
    entry = _index()["no-course-points"]
    assert entry["entry_count"] == 2
    assert entry["pdf"]["rendered"] is True


def test_custom_instruction_tags_on_the_original_test_route():
    """Route 6260667 is the only known source of [Custom] and [End] tags.

    Seven course points plus two sentinels would be nine entries; the [End] tag
    consumes the synthesized end row via AdjustStartAndEnd, leaving six.
    """
    entry = _index()["unit-test-route"]
    assert entry["ok"]
    assert entry["route_name"] == "Roboviva Unit Test Route"
    assert entry["pdf"]["rendered"] is True
    tex = load_golden_text(entry["tex"])
    assert r"\textbf{Custom}" in tex, "the [Custom] tag reaches the Go column"


def test_a_real_public_route_cannot_be_rendered_at_all():
    """Route 5334050 is a live, public route that Roboviva cannot produce.

    "Around the block... with calculus!" has LaTeX math typed into its cue
    notes as a joke. The escaping does its job -- every backslash and brace is
    neutralized, so none of the author's math executes -- but the '^' in
    "^{\\frac{\\pi}{2}}" and "^2dx" is NOT escaped, and LaTeX treats a bare
    caret as a superscript operator outside math mode. The compile aborts and
    no PDF is written.

    So the injection boundary holds and the completeness of the escape set does
    not. A rider hitting this sees only "Guru Meditation: 0xFF".
    """
    entry = _index()["calculus-block"]
    assert entry["ok"], "parsing succeeds; only rendering fails"
    assert entry["pdf"]["rendered"] is False
    assert any("Missing $ inserted" in line
               for line in entry["pdf"]["error_excerpt"])

    # The author's markup is neutralized rather than executed.
    tex = load_golden_text(entry["tex"])
    assert r"\textbackslash sum" in tex
    assert r"\sum{" not in tex, "the raw command must not survive escaping"


@pytest.mark.parametrize("name", ["greek-name", "japanese-name-and-body"])
def test_non_latin_routes_cannot_be_rendered(name):
    """Two real public routes are unrenderable because of their alphabet.

    A Greek brevet and a Japanese 200km both parse perfectly and then fail in
    pdflatex, because inputenc has no mapping for their characters. This is a
    limitation of the LaTeX backend, and one of the stronger arguments for the
    rewrite: a Unicode-capable renderer fixes it without any roboviva-side work.
    """
    entry = _index()[name]
    assert entry["ok"], "parsing succeeds"
    assert entry["pdf"]["rendered"] is False
    assert any("inputenc" in line for line in entry["pdf"]["error_excerpt"])


def test_eight_of_eleven_real_routes_render():
    """A blunt summary of where the product actually stands.

    Three of eleven real public routes produce no PDF: one from an unescaped
    caret, two from non-Latin text. If a rewrite improves this ratio, that is
    an intentional divergence worth recording in KNOWN_DIVERGENCES.md rather
    than a broken test.
    """
    idx = _index()
    rendered = [n for n, g in idx.items()
                if g["ok"] and g["pdf"].get("rendered")]
    failed = sorted(set(idx) - set(rendered))
    assert len(idx) == 11
    assert failed == ["calculus-block", "greek-name",
                      "japanese-name-and-body"], failed

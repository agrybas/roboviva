"""Opt-in canary: has RideWithGPS changed shape under the fixtures?

Excluded from the default run. The parity suite is entirely offline, which is
what makes it deterministic -- but it also means a change at RideWithGPS goes
unnoticed until someone regenerates fixtures.

    pytest harness/tests -m live

These tests assert only the SHAPE of the response and that the routes are still
public. They deliberately say nothing about values or ETags, both of which
drift for legitimate reasons (a route gets edited; the server changes its hash).

A failure here does not mean the rewrite is broken. It means the recorded
fixtures no longer describe the live service, and someone needs to decide
whether to re-record them.
"""
import glob
import json
import os
import urllib.request

import pytest

from conftest import CORPUS

pytestmark = pytest.mark.live

# Byte-identical to ridewithgps.py:89 -- including the api_key parameter, which
# is what makes the response come back wrapped.
URL = "http://ridewithgps.com/routes/%s.json?api_key=%s&version=2"


def _fixtures():
    out = []
    for path in sorted(glob.glob(os.path.join(CORPUS, "approval", "*.json"))):
        with open(path, encoding="utf-8") as fh:
            fx = json.load(fh)
        out.append(pytest.param(fx, id=fx["slug"]))
    return out


def _fetch(route_id):
    with urllib.request.urlopen(URL % (route_id, None), timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


@pytest.mark.parametrize("fx", _fixtures())
def test_route_is_still_public_and_wrapped(fx):
    """The route still exists, is public, and still returns the wrapped shape.

    If this fails with a 404, the route was deleted or made private and needs
    replacing in the approval set. If it fails on the shape assertion,
    RideWithGPS changed its response format and the parser needs revisiting.
    """
    live = _fetch(fx["route_id"])

    assert "route" in live, (
        "response is no longer wrapped in a 'route' object -- the api_key "
        "parameter may have stopped having this effect, which would break "
        "ridewithgps.py:122")
    route = live["route"]
    assert "metrics" in route, "metrics object gone; ridewithgps.py:158 reads it"
    for key in ("distance", "ele_gain"):
        assert key in route["metrics"], "metrics.%s gone" % key
    assert "course_points" in route
    assert "name" in route


@pytest.mark.parametrize("fx", _fixtures())
def test_course_point_fields_are_unchanged(fx):
    """Course points still use 't' / 'd' / 'n' / 'description'.

    These four keys are the entire input vocabulary (ridewithgps.py:136-144).
    A rename upstream would break parsing silently -- 'n' missing just yields
    an empty description rather than an error.
    """
    route = _fetch(fx["route_id"])["route"]
    points = route.get("course_points") or []
    if not points:
        pytest.skip("route has no course points (%s)" % fx["slug"])

    for point in points:
        assert "t" in point, "instruction type key 't' missing"
        assert "d" in point, "distance key 'd' missing"
    assert any("n" in p for p in points), "no course point has 'n'"


@pytest.mark.parametrize("fx", _fixtures())
def test_recorded_content_still_matches(fx):
    """Warn -- via failure -- if a route's cue content was edited.

    Several approval routes are dated 2026 club rides that their owners may
    well revise. This is not a correctness failure; it means the goldens
    describe a version of the route that no longer exists, and the fixture
    should be re-recorded with:

        python3 harness/oracle/record_fixtures.py --force
    """
    live = _fetch(fx["route_id"])["route"]
    recorded = json.loads(fx["response"]["body"])["route"]

    assert len(live.get("course_points") or []) == \
        len(recorded.get("course_points") or []), (
            "%s: cue count changed (%d recorded, %d live) -- re-record"
            % (fx["slug"], len(recorded.get("course_points") or []),
               len(live.get("course_points") or [])))
    assert live.get("name") == recorded.get("name"), "route was renamed"


def test_csv_endpoint_no_longer_serves_csv():
    """routes/<id>.csv does not return CSV any more.

    What it returns instead depends on how you ask: a plain urllib request gets
    HTTP 401, while a browser-shaped request gets the route's HTML page. Either
    way getETagAndCuesheet_viaCSV cannot work -- the 401 becomes
    RideWithGpsError("Unknown Route ID"), and the HTML gets far enough into the
    parser to raise a bare TypeError from float(None).

    If this ever starts returning CSV again, getETagAndCuesheet_viaCSV becomes
    revivable and the "probably delete" note in KNOWN_DIVERGENCES.md should be
    revisited.
    """
    url = "http://ridewithgps.com/routes/6260667.csv"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            head = resp.read(400).decode("utf-8", "replace").lstrip().lower()
    except urllib.error.HTTPError as exc:
        assert exc.code in (401, 403, 404), (
            "unexpected status from the CSV endpoint: %s" % exc.code)
        return

    assert not head.startswith("type,"), (
        "the CSV endpoint appears to serve CSV again: %r" % head[:120])

#!/usr/bin/env python3
"""Record RideWithGPS responses as committed fixtures.

This is the ONLY part of the harness that touches the network. Everything else
reads what this writes, so the parity suite stays deterministic and offline.

Run it deliberately, not as part of a test:

    python3 harness/oracle/record_fixtures.py            # record any missing
    python3 harness/oracle/record_fixtures.py --force    # re-record everything

The URL below is byte-for-byte the one the legacy code builds at
ridewithgps.py:89, including the literal `api_key=None` that the default
argument interpolates. That parameter is load-bearing: with it RWGPS returns
the wrapped {"route": {..., "metrics": {...}}} shape the parser reads, and
without it -- at any `version` value -- it returns a flat object the parser
cannot handle. Do not "clean it up".
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.normpath(os.path.join(HERE, "..", "corpus", "approval"))

# Byte-identical to ridewithgps.py:89.
URL = "http://ridewithgps.com/routes/%s.json?api_key=%s&version=2"

# Each entry: (route_id, slug, why it earns a place in the approval set).
ROUTES = [
    (54079314, "ac1-westwood",
     "Smallest real production route. Generic sentinel, Food, and a '>' in a "
     "description exercising the asymmetric $\\Rightarrow$ escape."),
    (54141896, "ac2-ridgewood",
     "Slight Left/Slight Right volume; U+200B zero-width spaces in RWGPS's "
     "'Philips Pkwy/<ZWSP>Van Riper' street-name joins."),
    (47438923, "wild-things",
     "Escaping regression route: '&' and U+200B together. Adds Sharp Left/"
     "Sharp Right (which _cleanDescription does NOT strip), Control, Water. "
     "Multi-page."),
    (55132669, "ac12-gunks-and-roses",
     "Richest instruction mix: Summit x3 (climb glyph), Danger x3 + Food/Water "
     "(colored rows), and three UNMAPPED types -- Climb, Uturn, Valley -- "
     "exercising the passthrough branch at ridewithgps.py:294."),
    (6260667, "unit-test-route",
     "The original fixture and the only known source of [Custom] and [End] "
     "bracket tags: custom-instruction override plus AdjustStartAndEnd."),
    (5334050, "calculus-block",
     "LaTeX escaping torture test -- #, backslash, _, {, } all present in "
     "genuine descriptions. Tiny, stays in the fast tier."),
    (5424696, "six-gaps",
     "Longest and densest: Summit x5, Water x3, Food x3, Danger. Drives "
     "multi-page two-column flow and \\pageref{LastPage}."),
    (56819245, "effin-200",
     "Real-world LOWERCASE 'right'/'left' course-point types (from 'Keep "
     "right'/'Keep left'), proving the case-sensitive mapping falls through to "
     "literal passthrough in production. Also Uturn."),
    (5011296, "no-course-points",
     "Degenerate route with zero course points -- the cue sheet is only the "
     "two synthesized Start/End sentinels."),
    (56811933, "greek-name",
     "Greek in the route NAME, which lands in \\lhead. Expected to stress the "
     "pdflatex/Helvetica font stack."),
    (56784512, "japanese-name-and-body",
     "Japanese in the name AND every description, separating 'name' unicode "
     "from 'body' unicode. Expected to stress the font stack."),
]


def fetch(route_id):
    url = URL % (route_id, None)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
        return {
            "status": resp.status,
            "final_url": resp.url,
            "etag": resp.headers.get("ETag"),
            "content_type": resp.headers.get("Content-Type"),
            "body": body,
        }


def strip_track_points(body):
    """Drop route.track_points from a recorded body.

    track_points is the raw GPS polyline -- thousands of {x,y,e,d} samples that
    make up ~93% of the payload. The legacy parser never reads it:
    getETagAndCuesheet_viaJSON touches only route.name, route.course_points,
    route.metrics.distance and route.metrics.ele_gain (ridewithgps.py:122-171).

    Removing it keeps fixtures reviewable in a diff. The provenance block
    records the original byte length and SHA-256 so the edit stays auditable,
    and re-running with --force against the live API reproduces it.
    """
    parsed = json.loads(body)
    route = parsed.get("route")
    n_dropped = 0
    if isinstance(route, dict) and "track_points" in route:
        n_dropped = len(route.pop("track_points") or [])
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True), n_dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="re-record fixtures that already exist")
    args = ap.parse_args()

    os.makedirs(CORPUS, exist_ok=True)
    failures = []

    for route_id, slug, why in ROUTES:
        path = os.path.join(CORPUS, "%s-%d.json" % (slug, route_id))
        if os.path.exists(path) and not args.force:
            print("skip    %s (exists)" % os.path.basename(path))
            continue
        try:
            got = fetch(route_id)
        except Exception as exc:  # noqa: BLE001 - report and keep going
            print("FAIL    %-14s %s" % (slug, exc))
            failures.append((route_id, slug, str(exc)))
            continue

        raw_body = got["body"]
        slim_body, n_dropped = strip_track_points(raw_body)
        got["body"] = slim_body

        parsed = json.loads(slim_body)
        route = parsed.get("route") or {}
        n_points = len(route.get("course_points") or [])

        fixture = {
            "route_id": route_id,
            "slug": slug,
            "why": why,
            "request_url": URL % (route_id, None),
            "provenance": {
                "recorded_from": "live ridewithgps.com",
                "original_body_bytes": len(raw_body.encode("utf-8")),
                "original_body_sha256": hashlib.sha256(
                    raw_body.encode("utf-8")).hexdigest(),
                "track_points_dropped": n_dropped,
                "note": "route.track_points removed; the legacy parser never "
                        "reads it (ridewithgps.py:122-171). Everything else is "
                        "verbatim, re-serialized with sorted keys.",
            },
            "response": got,
            # Denormalized for quick reading in review; the parser only ever
            # sees response.body.
            "summary": {
                "name": route.get("name"),
                "course_points": n_points,
                "metrics_distance_m": (route.get("metrics") or {}).get("distance"),
                "metrics_ele_gain_m": (route.get("metrics") or {}).get("ele_gain"),
                "visibility": route.get("visibility"),
            },
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(fixture, fh, indent=2, ensure_ascii=False, sort_keys=True)
            fh.write("\n")
        print("record  %-34s pts=%-4d %s" % (
            os.path.basename(path), n_points, route.get("name")))

    if failures:
        print("\n%d fixture(s) failed:" % len(failures), file=sys.stderr)
        for route_id, slug, err in failures:
            print("  %s (%s): %s" % (route_id, slug, err), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

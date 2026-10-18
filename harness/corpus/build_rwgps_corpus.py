#!/usr/bin/env python3
"""Generate the RideWithGPS ingestion and fetch corpus.

Separate from build_corpus.py because these cases are built from the recorded
approval fixtures in corpus/approval/, which have to exist first:

    python3 harness/oracle/record_fixtures.py
    python3 harness/corpus/build_rwgps_corpus.py
"""
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
APPROVAL = os.path.join(HERE, "approval")

# Byte-identical to ridewithgps.py:89.
JSON_URL = "http://ridewithgps.com/routes/%s.json?api_key=%s&version=2"

ZWSP = "​"


def case(name, why, **payload):
    d = {"name": name, "why": why}
    d.update(payload)
    return d


def ok(body, etag='W/"deadbeef"'):
    """One successful HTTP response in a script."""
    return {"status": 200, "headers": {"ETag": etag}, "body": body}


def legacy_body(route_name="R", course_points=None, distance_m=1609.344,
                ele_gain_m=100.0, **extra):
    """Build a RideWithGPS JSON body in the shape the parser expects.

    Wrapped under "route", with a "metrics" sub-object -- which is what the
    live API returns when `api_key` is present in the query string.
    """
    route = {
        "name": route_name,
        "course_points": course_points if course_points is not None else [],
        "metrics": {"distance": distance_m, "ele_gain": ele_gain_m},
    }
    route.update(extra)
    return json.dumps({"route": route, "type": "route"})


def cp(t="Right", n="Turn right onto Foo", d=100.0, description=None):
    """One RideWithGPS course point.

    Field names are RideWithGPS's, and two of them are inverted relative to
    roboviva's vocabulary: 'n' (RWGPS "note") becomes roboviva's DESCRIPTION,
    and 'description' becomes roboviva's NOTE (ridewithgps.py:136-141).
    """
    point = {"t": t, "n": n, "d": d}
    if description is not None:
        point["description"] = description
    return point


# ---------------------------------------------------------------------------
# Fetch semantics
# ---------------------------------------------------------------------------
_SIMPLE = legacy_body(course_points=[cp()], distance_m=1609.344)

FETCH_JSON = [
    case("happy_path",
         "One 200 with a well-formed body. Pins the request URL, which must "
         "contain the literal 'api_key=None' -- see api_key_omitted_breaks.",
         route_id=123, etag=None, script=[ok(_SIMPLE)]),

    case("conditional_request_sends_if_none_match",
         "A non-None etag is sent as If-None-Match (ridewithgps.py:91-92).",
         route_id=123, etag='W/"cached"', script=[ok(_SIMPLE)]),

    case("etag_empty_string_not_sent",
         "The guard is `if etag:`, so an empty string sends NO header -- an "
         "empty cached etag silently becomes an unconditional request.",
         route_id=123, etag="", script=[ok(_SIMPLE)]),

    case("not_modified_304",
         "304 returns (etag, None) and stops (ridewithgps.py:104-106). This is "
         "the whole point of the cache: no download and no pdflatex run.",
         route_id=123, etag='W/"cached"',
         script=[{"raise": "http", "status": 304}]),

    case("not_found_404",
         "Any non-304 HTTPError becomes RideWithGpsError('Unknown Route ID'), "
         "which the web layer turns into the 'not a valid route' page. Note a "
         "500 from RideWithGPS is reported to the rider as a bad route id.",
         route_id=123, etag=None,
         script=[{"raise": "http", "status": 404}]),

    case("server_error_500_reported_as_bad_route",
         "Same handler as 404 -- the message blames the route id regardless.",
         route_id=123, etag=None,
         script=[{"raise": "http", "status": 500}]),

    case("one_timeout_then_success",
         "socket.timeout is swallowed and the loop retries (ridewithgps.py:110).",
         route_id=123, etag=None,
         script=[{"raise": "timeout"}, ok(_SIMPLE)]),

    case("two_timeouts_then_success",
         "Second retry still succeeds; Max_Attempts is 3.",
         route_id=123, etag=None,
         script=[{"raise": "timeout"}, {"raise": "timeout"}, ok(_SIMPLE)]),

    case("three_timeouts_exhausts_retries",
         "All three attempts time out -> RideWithGpsError('No data ... after "
         "3 tries') (ridewithgps.py:113-114).",
         route_id=123, etag=None,
         script=[{"raise": "timeout"}] * 3),

    case("malformed_json",
         "json.loads failure -> RideWithGpsError with the raw body inlined "
         "into the message (ridewithgps.py:116-119).",
         route_id=123, etag=None, script=[ok("{not json")]),

    case("empty_body",
         "An empty 200 body is falsy, so it takes the 'No data' path rather "
         "than the JSON-decode path (ridewithgps.py:113).",
         route_id=123, etag=None, script=[ok("")]),

    case("api_key_omitted_breaks_parsing",
         "THE TRAP. Without api_key in the query string RideWithGPS returns a "
         "FLAT object -- name/course_points/distance at top level, no 'route' "
         "wrapper and no 'metrics'. The parser reads data['route'] at "
         "ridewithgps.py:122 and raises KeyError. A rewrite that 'cleans up' "
         "the stray api_key=None silently switches response shapes and breaks. "
         "Recorded as an executable warning.",
         route_id=123, etag=None,
         script=[ok(json.dumps({"name": "R", "course_points": [],
                                "distance": 1609.0, "elevation_gain": 30.0}))]),

    case("missing_metrics",
         "Wrapped but without 'metrics' -> KeyError from ridewithgps.py:158.",
         route_id=123, etag=None,
         script=[ok(json.dumps({"route": {"name": "R", "course_points": []}}))]),

    case("explicit_api_key",
         "Passing a real api_key changes the URL. Nothing in the repo ever "
         "does this, but the parameter exists.",
         route_id=123, etag=None, api_key="SECRET", script=[ok(_SIMPLE)]),
]

# ---------------------------------------------------------------------------
# JSON parsing / cue construction
# ---------------------------------------------------------------------------
PARSE_JSON = [
    case("no_course_points",
         "Zero course points still yields two entries: the synthesized 'Start "
         "of route' (ridewithgps.py:128-133) and 'End of route' (:159-164).",
         route_id=1, etag=None,
         script=[ok(legacy_body(course_points=[], distance_m=1609.344))]),

    case("single_point",
         "Start, the point, End -- the minimum interesting sheet.",
         route_id=1, etag=None,
         script=[ok(legacy_body(course_points=[cp(d=800.0)],
                                distance_m=1609.344))]),

    case("missing_n_field",
         "'n' absent -> description becomes '' (ridewithgps.py:138-139).",
         route_id=1, etag=None,
         script=[ok(legacy_body(course_points=[{"t": "Right", "d": 100.0}]))]),

    case("missing_description_field",
         "'description' absent -> note becomes '' via the None guard at "
         "ridewithgps.py:396-397.",
         route_id=1, etag=None,
         script=[ok(legacy_body(course_points=[cp(description=None)]))]),

    case("note_present",
         "RWGPS 'description' becomes roboviva's NOTE -- the field inversion.",
         route_id=1, etag=None,
         script=[ok(legacy_body(course_points=[cp(description="Bring cash")]))]),

    case("quick_turn_cluster",
         "Three points inside 0.1mi of each other all get Modifier.QUICK "
         "(ridewithgps.py:311-315).",
         route_id=1, etag=None,
         script=[ok(legacy_body(course_points=[
             cp(d=1000.0), cp(d=1050.0), cp(d=1100.0)], distance_m=2000.0))]),

    case("slight_turn_by_description",
         "'Keep|Bear|Slight ' at the start of the description forces SLIGHT, "
         "regardless of distance (ridewithgps.py:309-310).",
         route_id=1, etag=None,
         script=[ok(legacy_body(course_points=[
             cp(n="Bear right onto Foo", d=1000.0)], distance_m=2000.0))]),

    case("slight_case_sensitive",
         "The modifier regex has no re.I, so lowercase 'bear right' does NOT "
         "become SLIGHT -- it falls through to the distance check.",
         route_id=1, etag=None,
         script=[ok(legacy_body(course_points=[
             cp(n="bear right onto Foo", d=1000.0)], distance_m=2000.0))]),

    case("zero_distance_first_point",
         "A point at d=0 makes prev_absolute_distance 0.0, which is FALSY, so "
         "the QUICK check at ridewithgps.py:311 is skipped entirely.",
         route_id=1, etag=None,
         script=[ok(legacy_body(course_points=[cp(d=0.0), cp(d=50.0)],
                                distance_m=2000.0))]),

    case("custom_instruction_tag",
         "A [tag] overrides the instruction and clears the modifier, but the "
         "COLOR was already computed from the RWGPS type and is not "
         "recomputed (ridewithgps.py:380-388).",
         route_id=1, etag=None,
         script=[ok(legacy_body(course_points=[
             cp(t="Danger", n="[U] Sharp bend", d=1000.0)], distance_m=2000.0))]),

    case("start_tag_promotes_entry",
         "A [start] tag makes cue_utils.AdjustStartAndEnd replace the "
         "synthesized start row (ridewithgps.py:174).",
         route_id=1, etag=None,
         script=[ok(legacy_body(course_points=[
             cp(t="Generic", n="[start] Real start", d=100.0),
             cp(d=1000.0)], distance_m=2000.0))]),

    case("all_mapped_instruction_types",
         "Every RideWithGPS type the mapping knows about, in one route.",
         route_id=1, etag=None,
         script=[ok(legacy_body(course_points=[
             cp(t=t, n="Point %d" % i, d=500.0 * (i + 1))
             for i, t in enumerate([
                 "Left", "Slight Left", "Sharp Left", "Right", "Slight Right",
                 "Sharp Right", "Straight", "Food", "Water", "Danger",
                 "Generic", "Control", "Summit", "4th Category",
                 "3rd Category", "2nd Category", "1st Category",
                 "Hors Category", "First Aid"])],
             distance_m=20000.0))]),

    case("unmapped_instruction_types",
         "Uturn / Climb / Valley and lowercase right/left, all seen in real "
         "public routes today, all passed through as literal strings.",
         route_id=1, etag=None,
         script=[ok(legacy_body(course_points=[
             cp(t="Uturn", n="Make a U-turn", d=500.0),
             cp(t="Climb", n="Steep climb ahead", d=1000.0),
             cp(t="Valley", n="Descend", d=1500.0),
             cp(t="right", n="Keep right", d=2000.0),
             cp(t="left", n="Keep left", d=2500.0)], distance_m=3000.0))]),

    case("unicode_and_zwsp",
         "Non-ASCII plus a zero-width space, as RideWithGPS actually emits.",
         route_id=1, etag=None,
         script=[ok(legacy_body(
             route_name="Rue de l'Église",
             course_points=[cp(n="Turn right onto A/" + ZWSP + "B", d=500.0),
                            cp(n="Straße", d=1000.0)],
             distance_m=2000.0))]),

    case("zero_elevation_gain",
         "ele_gain of 0 is falsy, so _makeHeader omits the ft figure entirely.",
         route_id=1, etag=None,
         script=[ok(legacy_body(course_points=[cp()], ele_gain_m=0.0))]),

    case("unit_conversion",
         "Pins Miles_Per_Meter=0.000621371192 and Feet_Per_Meter=3.28084 "
         "(ridewithgps.py:124-125) against exact metric inputs.",
         route_id=1, etag=None,
         script=[ok(legacy_body(course_points=[cp(d=1609.344)],
                                distance_m=1609.344, ele_gain_m=304.8))]),
]

# ---------------------------------------------------------------------------
# CSV path -- unreachable from the app, still public API
# ---------------------------------------------------------------------------
_CSV_HEADER = "Type,Notes,Distance,Elevation,Description"

CSV = [
    case("basic",
         "The CSV path builds a Route with NO name and NO elevation, and does "
         "NOT call AdjustStartAndEnd (ridewithgps.py:235-238) -- materially "
         "different output from the JSON path for the same route.",
         route_id=1, etag=None,
         script=[ok("\n".join([_CSV_HEADER,
                               "Start,Start of route,0.0,0,",
                               "Right,Turn right on A,1.0,10,",
                               "Left,Turn left on B,2.0,20,note here"]))]),

    case("header_pruned",
         "rows[1:] drops the first row unconditionally (ridewithgps.py:229), "
         "so a headerless CSV silently loses its first cue.",
         route_id=1, etag=None,
         script=[ok("\n".join(["Start,Start of route,0.0,0,",
                               "Right,Turn right on A,1.0,10,"]))]),

    case("embedded_newline_in_quoted_field",
         "The body is split on '\\n' BEFORE csv.DictReader sees it "
         "(ridewithgps.py:226). DictReader still reassembles the quoted field "
         "by pulling the next list item, so the row is NOT torn apart -- but "
         "the newline inside the field is silently swallowed, and 'Turn "
         "right,\\nthen immediately left' arrives as 'Turn right,then "
         "immediately left' with no separator.",
         route_id=1, etag=None,
         script=[ok("\n".join([_CSV_HEADER,
                               'Right,"Turn right,',
                               'then immediately left",1.0,10,']))]),

    case("trailing_blank_line",
         "A trailing newline produces an empty final row.",
         route_id=1, etag=None,
         script=[ok("\n".join([_CSV_HEADER, "Right,A,1.0,10,", ""]))]),

    case("not_modified_304",
         "Same conditional-GET contract as the JSON path.",
         route_id=1, etag='W/"cached"',
         script=[{"raise": "http", "status": 304}]),

    case("html_instead_of_csv",
         "What the live endpoint returns TODAY: ridewithgps.com/routes/<id>.csv "
         "serves an HTML page, with or without api_key, so this function is "
         "dead against the real service. It does fail rather than producing "
         "garbage -- but with a bare TypeError from float(None), not a "
         "RideWithGpsError, so the web layer reports it as the generic 0xFA "
         "'Error querying RideWithGPS' page.",
         route_id=1, etag=None,
         script=[ok("<!DOCTYPE html>\n<html class='' lang='en'>\n<head>\n"
                    "<title>Ride with GPS</title>\n</head>\n</html>")]),
]


def approval_cases():
    """One fetch case per recorded approval route."""
    out = []
    for path in sorted(glob.glob(os.path.join(APPROVAL, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            fx = json.load(fh)
        out.append(case(
            fx["slug"],
            fx["why"],
            route_id=fx["route_id"],
            etag=None,
            script=[{"status": 200,
                     "headers": {"ETag": fx["response"]["etag"]},
                     "body": fx["response"]["body"]}],
        ))
    return out


WRITERS = [
    ("rwgps/fetch_json.json", FETCH_JSON),
    ("rwgps/parse_json.json", PARSE_JSON),
    ("rwgps/fetch_csv.json", CSV),
    ("rwgps/approval.json", approval_cases()),
]


def main():
    total = 0
    for relpath, cases in WRITERS:
        if not cases:
            raise SystemExit(
                "%s is empty -- run harness/oracle/record_fixtures.py first"
                % relpath)
        names = [c["name"] for c in cases]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise SystemExit("duplicate case names in %s: %s" % (relpath, dupes))
        path = os.path.join(HERE, relpath)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(cases, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print("%-40s %3d cases" % (relpath, len(cases)))
        total += len(cases)
    print("%-40s %3d cases" % ("TOTAL", total))


if __name__ == "__main__":
    main()

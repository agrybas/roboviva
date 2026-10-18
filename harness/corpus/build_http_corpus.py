#!/usr/bin/env python3
"""Generate the HTTP endpoint and CLI scenario corpus.

A scenario is an ordered list of steps against the legacy Flask app, run with
everything controlled: a frozen clock, a scratch PDF cache and shelve file, a
scripted RideWithGPS, and a counting stand-in for pdflatex.

    python3 harness/corpus/build_http_corpus.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def case(name, why, **payload):
    d = {"name": name, "why": why}
    d.update(payload)
    return d


def body(name="Probe Route", n_points=1, distance_m=1609.344, ele_gain_m=100.0):
    points = [{"t": "Right", "n": "Turn right onto Street %d" % i,
               "d": 400.0 * (i + 1)} for i in range(n_points)]
    return json.dumps({"route": {"name": name, "course_points": points,
                                 "metrics": {"distance": distance_m,
                                             "ele_gain": ele_gain_m}}})


def ok(etag='W/"v1"', **kw):
    return {"status": 200, "headers": {"ETag": etag}, "body": body(**kw)}


def get(path, method="GET"):
    return {"do": "get", "path": path, "method": method}


def advance(seconds):
    return {"do": "advance_clock", "seconds": seconds}


HTTP = [
    # -- the landing page -------------------------------------------------
    case("index",
         "GET /roboviva/ serves static/index.html through send_static_file "
         "(views.py:31-33).",
         steps=[get("/roboviva/")], script=[]),

    case("static_asset_two_ways",
         "robo.css answers at BOTH /roboviva/robo.css (blueprint static, "
         "static_url_path='') and /robo.css (app static, also ''). Two mounts "
         "for the same directory, which a rewrite is likely to collapse.",
         steps=[get("/roboviva/robo.css"), get("/robo.css")], script=[]),

    # -- the main flow ----------------------------------------------------
    case("fresh_route_redirects_to_pdf",
         "A route with no cache entry: fetch, render, store, 302 to the PDF.",
         steps=[get("/roboviva/routes/123")], script=[ok()]),

    case("regeneration_runs_pdflatex_twice",
         "THE DOUBLE RENDER. views.py:87 computes pdf_data, then views.py:102 "
         "calls latex2pdf(latex) AGAIN inside the open() block and writes that "
         "second result -- the first is discarded. Every cache miss pays for "
         "two full pdflatex runs. Almost certainly a copy-paste slip; pinned "
         "so the rewrite drops it deliberately.",
         steps=[get("/roboviva/routes/123")], script=[ok()]),

    case("unchanged_etag_skips_rendering",
         "Second request with the same ETag: RideWithGPS answers 304, so no "
         "LaTeX and no pdflatex. This is what the cache is for.",
         steps=[get("/roboviva/routes/123"), get("/roboviva/routes/123")],
         script=[ok(), {"raise": "http", "status": 304}]),

    case("changed_etag_regenerates",
         "The route was edited: a new ETag means a fresh render, so four "
         "pdflatex calls across two requests.",
         steps=[get("/roboviva/routes/123"), get("/roboviva/routes/123")],
         script=[ok(etag='W/"v1"'), ok(etag='W/"v2"', name="Edited Route")]),

    # -- serving the PDF ---------------------------------------------------
    case("pdf_served_inline",
         "send_from_directory with as_attachment=False (views.py:125-129). "
         "Whether a Content-Disposition header appears at all differs between "
         "Flask 1.x and modern Flask, so it is recorded explicitly.",
         steps=[get("/roboviva/routes/123"), get("/roboviva/pdfs/123.pdf")],
         script=[ok()]),

    case("missing_pdf_renders_regen_page",
         "A cached DB entry whose file is gone: GET /pdfs/<id>.pdf returns the "
         "regen page with HTTP 200, NOT a 404 (views.py:123-124).",
         steps=[get("/roboviva/pdfs/999.pdf")], script=[]),

    case("pdf_deleted_after_caching",
         "The realistic version: render, delete the file, request it again.",
         steps=[get("/roboviva/routes/123"),
                {"do": "delete_pdf", "route_id": 123},
                get("/roboviva/pdfs/123.pdf")],
         script=[ok()]),

    # -- error branches, all of which return HTTP 200 ----------------------
    case("invalid_route_id_error_page",
         "RideWithGpsError -> the 'is not a valid RideWithGPS Route' page at "
         "HTTP 200 (views.py:54-56). A 404 would be more honest but would let "
         "the browser show its own error page instead of the styled one.",
         steps=[get("/roboviva/routes/123")],
         script=[{"raise": "http", "status": 404}]),

    case("upstream_500_also_blames_the_route_id",
         "Any non-304 HTTPError is turned into RideWithGpsError, so a "
         "RideWithGPS outage is reported to the rider as a bad route number.",
         steps=[get("/roboviva/routes/123")],
         script=[{"raise": "http", "status": 500}]),

    case("generic_fetch_failure_guru_0xFA",
         "A non-RideWithGpsError exception -> 'Guru Meditation: 0xFA' "
         "(views.py:57-61). Reached here by a malformed payload that makes the "
         "parser raise KeyError -- the same failure a missing api_key causes.",
         steps=[get("/roboviva/routes/123")],
         script=[{"status": 200, "headers": {"ETag": 'W/"x"'},
                  "body": json.dumps({"name": "flat shape", "course_points": []})}]),

    case("pdf_render_failure_guru_0xFF",
         "latex2pdf raising -> 'Guru Meditation: 0xFF' (views.py:88-94).",
         steps=[get("/roboviva/routes/123")], script=[ok()], pdf_fails=True),

    case("unwritable_cache_dir_guru_0xCE",
         "PDF_CACHE_DIR missing -> 'Guru Meditation: 0xCE' (views.py:103-108). "
         "Reachable on a fresh clone: pdf_cache/ is gitignored and the app "
         "never creates it, so the very first request fails this way.",
         steps=[get("/roboviva/routes/123")], script=[ok()], no_cache_dir=True),

    # -- the cache admin surface -------------------------------------------
    case("cache_empty",
         "GET /roboviva/cache on a cold start (views.py:131-161).",
         steps=[get("/roboviva/cache")], script=[]),

    case("cache_age_seconds", "Age < 60 renders as '%d sec'.",
         steps=[get("/roboviva/routes/123"), advance(30), get("/roboviva/cache")],
         script=[ok()]),

    case("cache_age_minutes", "60 < age < 3600 renders as '%d min'.",
         steps=[get("/roboviva/routes/123"), advance(600), get("/roboviva/cache")],
         script=[ok()]),

    case("cache_age_hours", "3600 < age < 86400 renders as '%d hr'.",
         steps=[get("/roboviva/routes/123"), advance(7200), get("/roboviva/cache")],
         script=[ok()]),

    case("cache_age_days", "age > 86400 renders as '%.1f days'.",
         steps=[get("/roboviva/routes/123"), advance(200000),
                get("/roboviva/cache")],
         script=[ok()]),

    case("cache_age_exactly_60",
         "BOUNDARY: the chain is `< 60`, then `> 60 and < 3600`, so exactly 60 "
         "matches NOTHING and falls through to the days branch -- a "
         "one-minute-old entry is reported as '0.0 days' (views.py:148-155). "
         "Same hole at exactly 3600 and 86400.",
         steps=[get("/roboviva/routes/123"), advance(60), get("/roboviva/cache")],
         script=[ok()]),

    case("cache_age_exactly_3600", "The second boundary hole.",
         steps=[get("/roboviva/routes/123"), advance(3600),
                get("/roboviva/cache")],
         script=[ok()]),

    case("cache_age_exactly_86400", "The third boundary hole.",
         steps=[get("/roboviva/routes/123"), advance(86400),
                get("/roboviva/cache")],
         script=[ok()]),

    case("cache_multiple_entries_sorted",
         "Rows are sorted by (timestamp, route_id, etag) (views.py:142), so "
         "oldest first.",
         steps=[get("/roboviva/routes/111"), advance(10),
                get("/roboviva/routes/222"), advance(10),
                get("/roboviva/routes/333"), get("/roboviva/cache")],
         script=[ok(etag='W/"a"'), ok(etag='W/"b"'), ok(etag='W/"c"')]),

    case("cache_remove_hit",
         "Removes the DB entry -- but NOT the PDF file (views.py:163-173), so "
         "the file is orphaned on disk with nothing tracking it.",
         steps=[get("/roboviva/routes/123"), get("/roboviva/cache/remove/123"),
                get("/roboviva/cache"), get("/roboviva/pdfs/123.pdf")],
         script=[ok()]),

    case("cache_remove_miss", "Removing an unknown id is a no-op with a message.",
         steps=[get("/roboviva/cache/remove/999")], script=[]),

    case("cache_purge_deletes_old",
         "Entries older than the threshold lose both DB row and file "
         "(views.py:193-204).",
         steps=[get("/roboviva/routes/123"), advance(10000),
                get("/roboviva/cache/purge/3600"), get("/roboviva/cache")],
         script=[ok()]),

    case("cache_purge_retains_fresh",
         "Entries newer than the threshold are counted, not deleted.",
         steps=[get("/roboviva/routes/123"), advance(60),
                get("/roboviva/cache/purge/3600"), get("/roboviva/cache")],
         script=[ok()]),

    case("cache_purge_missing_pdf_raises_500",
         "BUG: the retain branch calls os.stat unguarded (views.py:206), so a "
         "DB entry whose PDF was deleted -- exactly the state /cache/remove "
         "cannot create but a manual cleanup can -- takes the whole endpoint "
         "down with an unhandled OSError. The only 5xx in the app.",
         steps=[get("/roboviva/routes/123"),
                {"do": "delete_pdf", "route_id": 123},
                get("/roboviva/cache/purge/3600")],
         script=[ok()]),

    # -- routing and method handling ---------------------------------------
    case("non_numeric_route_id_404",
         "<int:route_id> rejects non-numeric segments before any handler runs, "
         "so this is a real Flask 404 rather than the styled error page.",
         steps=[get("/roboviva/routes/abc")], script=[]),

    case("negative_route_id_404",
         "The int converter rejects '-1' too (no negative support by default).",
         steps=[get("/roboviva/routes/-1")], script=[]),

    case("post_not_allowed",
         "No route declares methods=, so everything is GET/HEAD/OPTIONS only. "
         "The whole service is read-only and unauthenticated -- including the "
         "cache admin endpoints, which anyone can call.",
         steps=[get("/roboviva/cache", method="POST")], script=[]),

    case("head_and_options_allowed",
         "Flask adds HEAD and OPTIONS automatically.",
         steps=[get("/roboviva/cache", method="HEAD"),
                get("/roboviva/cache", method="OPTIONS")], script=[]),

    case("unknown_path_404", "Nothing catches unknown paths.",
         steps=[get("/roboviva/nope")], script=[]),
]

CLI = [
    case("make_latex_no_args",
         "Wrong argc prints usage and returns 1 (make_latex.py:23-25).",
         script_name="make_latex.py", argv=[], script=[]),

    case("make_latex_too_many_args", "Same guard, other direction.",
         script_name="make_latex.py", argv=["1", "2"], script=[]),

    case("make_latex_non_numeric",
         "int(argv[1]) raises ValueError -- an uncaught traceback, not a "
         "friendly message (make_latex.py:27).",
         script_name="make_latex.py", argv=["abc"], script=[]),

    case("make_latex_happy",
         "stdout is NOT pure LaTeX: two '%'-prefixed progress lines precede "
         "the document (make_latex.py:28-32). They are valid LaTeX comments, "
         "so piping to pdflatex still works -- which is presumably the point.",
         script_name="make_latex.py", argv=["123"], script=[ok()]),

    case("make_pdf_no_args", "Usage and exit 1 (make_pdf.py:23-25).",
         script_name="make_pdf.py", argv=[], script=[]),

    case("make_pdf_happy",
         "Writes <route_id>.pdf into the CWD. Unlike make_latex.py the "
         "progress text is NOT comment-escaped, since it goes to a terminal "
         "rather than a pipe (make_pdf.py:28-38).",
         script_name="make_pdf.py", argv=["123"], script=[ok()]),
]

WRITERS = [
    ("http/endpoints.json", HTTP),
    ("cli/scripts.json", CLI),
]


def main():
    total = 0
    for relpath, cases in WRITERS:
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

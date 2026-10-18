"""Parity tests for the HTTP surface (roboviva/views.py).

Six GET routes under /roboviva, plus static assets. No POST, no auth, no CSRF,
no JSON API -- the entire service is "give me a route number, get a PDF".

Everything is controlled during these scenarios: a frozen clock (so the /cache
age strings are assertable), a scratch cache directory and shelve file, a
scripted RideWithGPS, and a counting stand-in for pdflatex.
"""
import re

import pytest

from conftest import assert_matches, load_golden, paired


def _scenario(name):
    for g in load_golden("http/endpoints.json"):
        if g["name"] == name:
            assert g["ok"], "scenario itself failed: %s" % g.get("error")
            return g["result"]
    raise AssertionError("no golden named %r" % name)


def _http_steps(name):
    return [r for r in _scenario(name)["responses"] if "status" in r]


def _main_text(body):
    """Pull the message out of an error.html / regen.html render."""
    m = re.search(r'<span class="main-text">(.*?)</span>',
                  " ".join(body.split()), re.S)
    return m.group(1).strip() if m else ""


@pytest.mark.parametrize("case,expected", paired("http/endpoints.json"))
def test_endpoint_scenario(sut, case, expected):
    """Full request/response parity for every scenario in the corpus."""
    assert_matches(
        lambda: sut.http(case["steps"], case["script"],
                         pdf_fails=case.get("pdf_fails", False),
                         no_cache_dir=case.get("no_cache_dir", False)),
        expected, case)


# -- the main flow ---------------------------------------------------------

def test_route_request_redirects_to_the_pdf():
    """GET /roboviva/routes/<id> always ends in a 302 (views.py:115-116).

    The handler never serves the PDF itself; it renders, caches, and bounces
    the browser to the static-ish /pdfs/ URL. That is what makes a second visit
    cheap even without the ETag check.
    """
    steps = _http_steps("fresh_route_redirects_to_pdf")
    assert steps[0]["status"] == 302
    assert steps[0]["location"].endswith("/roboviva/pdfs/123.pdf")


def test_regeneration_invokes_pdflatex_twice():
    """QUIRK: every cache miss runs pdflatex twice.

    views.py:87 computes pdf_data, and views.py:102 then calls
    latex2pdf(latex) a SECOND time inside the open() block, writing that
    result and discarding the first. Two full TeX runs per render, one of them
    pure waste -- on a long route that is seconds of CPU.

    Pinned so the rewrite drops it as a decision rather than inheriting it.
    """
    assert _scenario("regeneration_runs_pdflatex_twice")["pdflatex_calls"] == 2


def test_unchanged_etag_skips_rendering_entirely():
    """The point of the cache: a 304 means no LaTeX and no pdflatex.

    Two requests, but only the first renders -- the count stays at 2 rather
    than rising to 4.
    """
    s = _scenario("unchanged_etag_skips_rendering")
    assert len(_http_steps("unchanged_etag_skips_rendering")) == 2
    assert s["pdflatex_calls"] == 2, "the second request must render nothing"


def test_changed_etag_triggers_a_fresh_render():
    """An edited route re-renders: 2 requests x 2 calls = 4."""
    assert _scenario("changed_etag_regenerates")["pdflatex_calls"] == 4


def test_conditional_request_is_sent_upstream():
    """The cached ETag is forwarded to RideWithGPS as If-None-Match.

    That is what lets the upstream answer 304 and saves the download as well
    as the render.
    """
    reqs = _scenario("unchanged_etag_skips_rendering")["rwgps_requests"]
    assert len(reqs) == 2
    assert not any(k.lower() == "if-none-match" for k in reqs[0]["headers"])
    assert any(k.lower() == "if-none-match" for k in reqs[1]["headers"])


# -- serving the PDF -------------------------------------------------------

def test_pdf_is_served_inline_as_application_pdf():
    """as_attachment=False, so the browser displays rather than downloads.

    On Flask 1.x that means no Content-Disposition header at all. Modern Flask
    emits 'inline; filename=...' instead -- a real behavior change the rewrite
    has to decide about, which is why the header is asserted explicitly.
    """
    step = _http_steps("pdf_served_inline")[1]
    assert step["status"] == 200
    assert step["content_type"] == "application/pdf"
    assert step["content_disposition"] is None, (
        "legacy Flask emits no Content-Disposition here; if the rewrite adds "
        "one, that is a deliberate change")


def test_missing_pdf_returns_the_regen_page_at_200():
    """A missing file is NOT a 404 (views.py:123-124).

    The rider gets a styled "make it again?" page linking back to
    /routes/<id>. Returning 200 for a missing resource is wrong by HTTP
    semantics but keeps the user in the app.
    """
    step = _http_steps("missing_pdf_renders_regen_page")[0]
    assert step["status"] == 200
    assert "doesn't exist" in step["body"]
    assert "/roboviva/routes/999" in step["body"], "links back to regenerate"


def test_deleted_pdf_falls_back_to_regen_page():
    """The realistic version: cached, then the file is cleaned up underneath."""
    steps = _http_steps("pdf_deleted_after_caching")
    assert steps[-1]["status"] == 200
    assert "doesn't exist" in steps[-1]["body"]


# -- error branches --------------------------------------------------------

@pytest.mark.parametrize("scenario,fragment", [
    ("invalid_route_id_error_page", "is not a valid RideWithGPS Route"),
    ("generic_fetch_failure_guru_0xFA", "{Guru Meditation: 0xFA}"),
    ("pdf_render_failure_guru_0xFF", "0xFF - Error Rendering PDF"),
    ("unwritable_cache_dir_guru_0xCE", "0xCE - Error writing PDF"),
])
def test_every_error_branch_returns_http_200(scenario, fragment):
    """All four failure paths render error.html with status 200.

    Never 4xx, never 5xx. The apparent motive is that a styled page beats
    whatever a browser or proxy would substitute -- but it also means
    monitoring cannot distinguish a broken service from a working one, and
    every failure is cached-as-success by any intermediary.
    """
    step = _http_steps(scenario)[0]
    assert step["status"] == 200, "error pages deliberately return 200"
    assert fragment in _main_text(step["body"]), _main_text(step["body"])


def test_upstream_outage_is_reported_as_a_bad_route_number():
    """A RideWithGPS 500 tells the rider their route id is invalid.

    ridewithgps.py:108-109 collapses every non-304 HTTPError into
    RideWithGpsError("Unknown Route ID"), so the rider is blamed for an
    upstream outage. Frozen because the text is user-visible; worth fixing.
    """
    step = _http_steps("upstream_500_also_blames_the_route_id")[0]
    assert "is not a valid RideWithGPS Route" in _main_text(step["body"])


def test_write_failure_happens_between_the_two_pdflatex_calls():
    """With no cache directory the count is 1, not 2.

    The first latex2pdf (views.py:87) succeeds; open() then fails at
    views.py:101 before the second call at :102 can run. A neat confirmation of
    exactly where the duplicated work sits.
    """
    assert _scenario("unwritable_cache_dir_guru_0xCE")["pdflatex_calls"] == 1


def test_missing_cache_dir_is_the_fresh_clone_experience():
    """pdf_cache/ is gitignored and the app never creates it.

    So a freshly cloned, freshly started Roboviva answers its very first route
    request with "Guru Meditation: 0xCE" until someone makes the directory by
    hand. Nothing in the README mentions this.
    """
    step = _http_steps("unwritable_cache_dir_guru_0xCE")[0]
    assert "0xCE" in _main_text(step["body"])


# -- the cache admin surface ----------------------------------------------

def test_cache_listing_when_empty():
    step = _http_steps("cache_empty")[0]
    assert step["status"] == 200
    assert "Cache has 0 entries" in step["body"]


@pytest.mark.parametrize("scenario,expected", [
    ("cache_age_seconds", "30 sec"),
    ("cache_age_minutes", "10 min"),
    ("cache_age_hours", "2 hr"),
    ("cache_age_days", "2.3 days"),
])
def test_cache_age_formatting(scenario, expected):
    """Ages render in four bands (views.py:147-155)."""
    body = _http_steps(scenario)[-1]["body"]
    assert "<td>%s</td>" % expected in body, body


@pytest.mark.parametrize("scenario", [
    "cache_age_exactly_60",
    "cache_age_exactly_3600",
])
def test_cache_age_boundaries_fall_through_to_days(scenario):
    """BUG, frozen: an age of exactly 60 or 3600 seconds renders as "0.0 days".

    The chain is `if age < 60 ... elif age > 60 and age < 3600 ... elif age >
    3600 and age < 86400 ... else`. The comparisons are strict on both sides,
    so the exact boundary values match no branch and land in the days case. A
    one-minute-old cache entry is displayed as "0.0 days" old.
    """
    body = _http_steps(scenario)[-1]["body"]
    assert "<td>0.0 days</td>" in body, (
        "expected the boundary to fall through to the days branch")


def test_cache_rows_are_sorted_oldest_first():
    """Sorted by (timestamp, route_id, etag) at views.py:142."""
    body = _http_steps("cache_multiple_entries_sorted")[-1]["body"]
    order = re.findall(r"<td>(\d{3})</td>", body)
    assert order == ["111", "222", "333"], order


def test_cache_remove_orphans_the_pdf_file():
    """/cache/remove deletes the DB row but leaves the file (views.py:163-173).

    The PDF stays on disk with nothing tracking it, so it is never purged --
    /cache/purge only iterates DB entries. Removing a route is therefore a
    slow disk leak.
    """
    steps = _http_steps("cache_remove_hit")
    assert "123 removed from cache" in steps[1]["body"]
    assert "Cache has 0 entries" in steps[2]["body"]
    assert steps[3]["content_type"] == "application/pdf", (
        "the orphaned file is still served")


def test_cache_remove_miss_is_harmless():
    assert "999 not found in cache" in _http_steps("cache_remove_miss")[0]["body"]


def test_purge_deletes_entries_past_the_threshold():
    steps = _http_steps("cache_purge_deletes_old")
    assert "DELETED" in steps[1]["body"]
    assert "Cache has 0 entries" in steps[2]["body"]


def test_purge_retains_fresh_entries():
    steps = _http_steps("cache_purge_retains_fresh")
    assert "DELETED" not in steps[1]["body"]
    assert "Cache has 1 entries" in steps[2]["body"]


def test_purge_500s_when_a_tracked_pdf_is_missing():
    """BUG, frozen: the only 5xx the app can produce.

    The retain branch calls os.stat unguarded (views.py:206). A DB entry whose
    file was removed by hand takes the entire endpoint down, and because the
    loop mutates the shelve while iterating, the failure point is not even
    deterministic across dbm backends.
    """
    steps = _http_steps("cache_purge_missing_pdf_raises_500")
    assert steps[-1]["status"] == 500


# -- routing and methods ---------------------------------------------------

@pytest.mark.parametrize("scenario", ["non_numeric_route_id_404",
                                      "negative_route_id_404",
                                      "unknown_path_404"])
def test_url_converter_rejects_bad_route_ids(scenario):
    """<int:route_id> rejects non-numeric and negative ids before any handler.

    This is why makeLatex's `'%d' % route_id` never blows up in the web app,
    even though the library itself accepts a string id quite happily.
    """
    assert _http_steps(scenario)[0]["status"] == 404


def test_service_is_read_only_and_unauthenticated():
    """No route declares methods=, so everything is GET/HEAD/OPTIONS.

    Worth stating plainly: /cache, /cache/remove/<id> and /cache/purge/<n> are
    unauthenticated administrative endpoints. Anyone who can reach the service
    can wipe its cache. Safe-ish (the data is a rebuildable derivative) but a
    real consideration for how the rewrite gets deployed.
    """
    step = _http_steps("post_not_allowed")[0]
    assert step["status"] == 405
    assert set(step["allow"].replace(" ", "").split(",")) == {
        "GET", "HEAD", "OPTIONS"}


def test_head_and_options_are_allowed():
    for step in _http_steps("head_and_options_allowed"):
        assert step["status"] == 200


def test_static_assets_answer_at_two_paths():
    """robo.css is reachable at /roboviva/robo.css and at /robo.css.

    Flask(static_url_path='') mounts roboviva/static at the app root, and the
    blueprint mounts the same folder again under its own prefix. Harmless, but
    a rewrite that serves assets once will change one of these URLs -- and
    index.html/tips.html use relative links that depend on the prefixed one.
    """
    for step in _http_steps("static_asset_two_ways"):
        assert step["status"] == 200, step["path"]

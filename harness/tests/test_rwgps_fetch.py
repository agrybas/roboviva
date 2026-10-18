"""Parity tests for the RideWithGPS HTTP layer (ridewithgps.py:68-238).

Driven by a scripted network stub, so retries, conditional GETs and timeouts
are deterministic and no test touches the real service.

Half the contract lives in the *request*, not the response -- the exact query
string, the 5-second timeout, the retry count, and whether If-None-Match is
sent. The stub records all of it and the goldens pin it.
"""
import pytest

from conftest import assert_matches, load_golden, paired


def _requests(golden_file, name):
    for g in load_golden(golden_file):
        if g["name"] == name:
            assert g["ok"], "op itself failed: %s" % g.get("error")
            return g["result"]["requests"]
    raise AssertionError("no golden named %r" % name)


def _result(golden_file, name):
    for g in load_golden(golden_file):
        if g["name"] == name:
            assert g["ok"], "op itself failed: %s" % g.get("error")
            return g["result"]
    raise AssertionError("no golden named %r" % name)


@pytest.mark.parametrize("case,expected", paired("rwgps/fetch_json.json"))
def test_fetch_json(sut, case, expected):
    """getETagAndCuesheet_viaJSON end to end against scripted responses."""
    assert_matches(
        lambda: sut.fetch_json(case["route_id"], case.get("etag"),
                               case["script"], case.get("api_key", "__unset__")),
        expected, case)


@pytest.mark.parametrize("case,expected", paired("rwgps/fetch_csv.json"))
def test_fetch_csv(sut, case, expected):
    """getETagAndCuesheet_viaCSV -- unreachable from the app, still public API.

    Kept in the harness because dropping it is a decision, not an oversight.
    See the html_instead_of_csv case: this function no longer works against the
    live service at all.
    """
    assert_matches(
        lambda: sut.fetch_csv(case["route_id"], case.get("etag"),
                              case["script"]),
        expected, case)


def test_request_url_carries_literal_api_key_none():
    """The query string must contain `api_key=None`, spelled exactly that way.

    ridewithgps.py:89 interpolates the DEFAULT argument (`api_key=None`) into
    the URL with %s, so every production request advertises the string "None"
    as its API key. It reads like a bug and is instead load-bearing: RideWithGPS
    returns the wrapped {"route": {..., "metrics": {...}}} shape only when an
    api_key parameter is present. Remove it and the response goes flat, and
    ridewithgps.py:122 raises KeyError.
    """
    url = _requests("rwgps/fetch_json.json", "happy_path")[0]["url"]
    assert url == ("http://ridewithgps.com/routes/123.json"
                   "?api_key=None&version=2")


def test_omitting_api_key_raises_keyerror():
    """The flat response shape is unparseable -- pinned as an executable warning."""
    r = _result("rwgps/fetch_json.json", "api_key_omitted_breaks_parsing")
    assert r["ok"] is False
    assert r["error"]["type"] == "KeyError"
    assert r["error"]["message"] == "'route'"


def test_request_uses_plain_http_and_five_second_timeout():
    """Plain http:// with a 5s timeout (ridewithgps.py:89,98).

    The scheme matters: the real endpoint 301-redirects http -> https, which
    urllib2 follows transparently on GET, so the ETag comes from the final
    response. A rewrite on a client that does not auto-follow would break.
    """
    req = _requests("rwgps/fetch_json.json", "happy_path")[0]
    assert req["url"].startswith("http://"), "not https in the legacy code"
    assert req["timeout"] == 5


def test_conditional_get_sends_if_none_match():
    """A cached etag becomes an If-None-Match header (ridewithgps.py:91-92)."""
    headers = _requests("rwgps/fetch_json.json",
                        "conditional_request_sends_if_none_match")[0]["headers"]
    assert any(k.lower() == "if-none-match" for k in headers), headers
    assert list(headers.values()) == ['W/"cached"']


def test_empty_etag_sends_no_conditional_header():
    """`if etag:` is a truthiness test, so '' silently disables the cache.

    Not reachable through the web layer today (shelve stores whatever the
    server sent), but a rewrite that normalizes a missing etag to '' instead of
    None would inherit this and quietly re-render every request.
    """
    headers = _requests("rwgps/fetch_json.json",
                        "etag_empty_string_not_sent")[0]["headers"]
    assert not any(k.lower() == "if-none-match" for k in headers), headers


def test_304_returns_etag_and_no_route():
    """304 short-circuits with (etag, None) (ridewithgps.py:104-106).

    This is the entire value of the cache: no body to parse and, upstream in
    views.handle_request, no pdflatex run.
    """
    r = _result("rwgps/fetch_json.json", "not_modified_304")
    assert r["ok"] is True
    assert r["route"] is None
    assert r["etag"] == 'W/"cached"'
    assert len(_requests("rwgps/fetch_json.json", "not_modified_304")) == 1


def test_retries_exactly_three_times_on_timeout():
    """Max_Attempts is 3 (ridewithgps.py:95-96), then RideWithGpsError."""
    name = "three_timeouts_exhausts_retries"
    r = _result("rwgps/fetch_json.json", name)
    assert r["ok"] is False
    assert r["error"]["type"] == "RideWithGpsError"
    assert r["error"]["message"] == "No data from RideWithGPS after 3 tries"
    assert len(_requests("rwgps/fetch_json.json", name)) == 3


def test_timeout_then_success_recovers():
    """A single timeout is transparent to the caller."""
    r = _result("rwgps/fetch_json.json", "one_timeout_then_success")
    assert r["ok"] is True
    assert r["route"] is not None
    assert len(_requests("rwgps/fetch_json.json",
                         "one_timeout_then_success")) == 2


def test_http_errors_all_report_unknown_route_id():
    """Every non-304 HTTPError becomes 'Unknown Route ID' (ridewithgps.py:108-109).

    So a RideWithGPS outage (500) is shown to the rider as "'123' is not a
    valid RideWithGPS Route" -- misleading, and worth revisiting in the
    rewrite. Frozen here because the error page text is user-visible.
    """
    for name in ("not_found_404", "server_error_500_reported_as_bad_route"):
        r = _result("rwgps/fetch_json.json", name)
        assert r["ok"] is False
        assert r["error"]["type"] == "RideWithGpsError"
        assert r["error"]["message"] == "Unknown Route ID: 123"


def test_malformed_and_empty_bodies_take_different_paths():
    """An empty body is 'no data'; a malformed one is 'decode error'.

    `if not raw_json` (ridewithgps.py:113) catches the empty string before
    json.loads ever runs, so the two failures produce different messages.
    """
    empty = _result("rwgps/fetch_json.json", "empty_body")
    malformed = _result("rwgps/fetch_json.json", "malformed_json")
    assert empty["error"]["message"].startswith("No data from RideWithGPS")
    assert malformed["error"]["message"].startswith("Error decoding JSON")


def test_csv_endpoint_returns_html_today():
    """ridewithgps.com/routes/<id>.csv serves an HTML page now.

    Confirmed against the live service with and without api_key, so
    getETagAndCuesheet_viaCSV cannot work against the real service any more.

    It does fail rather than silently producing a nonsense route -- but it
    fails as a bare TypeError out of float(None) in _rawCSVtoRWGPS_Entries
    (ridewithgps.py:336), not as a RideWithGpsError. Through the web layer that
    lands in the generic handler and shows the rider "Guru Meditation: 0xFA"
    instead of the specific bad-route message.
    """
    r = _result("rwgps/fetch_csv.json", "html_instead_of_csv")
    assert r["ok"] is False
    assert r["error"]["type"] == "TypeError", (
        "expected the unhelpful float() failure, not a domain error")


def test_csv_path_produces_no_name_and_no_elevation():
    """The CSV route is materially poorer than the JSON one.

    getETagAndCuesheet_viaCSV builds its Route without route_name or
    elevation_gain_ft (ridewithgps.py:235-237), and never calls
    AdjustStartAndEnd. The same route fetched two ways renders two different
    cue sheets -- the CSV one has no title and no climb figure in the header.
    """
    r = _result("rwgps/fetch_csv.json", "basic")
    assert r["route"]["name"] is None
    assert r["route"]["elevation_gain_ft"] is None


def test_csv_embedded_newline_is_swallowed_not_split():
    """Splitting on '\\n' before csv.DictReader mangles multi-line fields.

    ridewithgps.py:226 hands DictReader a pre-split list. DictReader still
    reassembles a quoted field spanning two items, so the row survives -- but
    the newline that separated them is gone, and the two halves are
    concatenated with no space: "Turn right,then immediately left".
    """
    r = _result("rwgps/fetch_csv.json", "embedded_newline_in_quoted_field")
    assert r["ok"] is True, "the row is not torn apart"
    descriptions = [e["description"] for e in r["route"]["entries"]]
    assert "Turn right,then immediately left" in descriptions

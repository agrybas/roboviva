"""Pytest wiring for the parity harness.

    pytest harness/tests --sut=legacy   # against the Python 2 original
    pytest harness/tests                # against the rewrite (default)
    pytest harness/tests -m live        # opt-in RideWithGPS shape canary

Tests compare the SUT against committed goldens produced by
harness/oracle/generate.py. They never recompute an expected value in Python --
if a golden is missing the test fails rather than inventing one, because a
harness that can silently manufacture its own expectations proves nothing.
"""
import json
import os

import pytest

from sut import Sut, make_backend

HARNESS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        ".."))
CORPUS = os.path.join(HARNESS, "corpus")
GOLDEN = os.path.join(HARNESS, "golden")


def pytest_addoption(parser):
    parser.addoption(
        "--sut", action="store", default=os.environ.get("ROBOVIVA_SUT", "new"),
        choices=["new", "legacy"],
        help="which implementation to test: 'new' (the rewrite, default) or "
             "'legacy' (the Python 2 original, via the oracle container)")


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live: hits ridewithgps.com; excluded unless -m live")


def pytest_collection_modifyitems(config, items):
    if config.getoption("-m") == "live":
        return
    skip_live = pytest.mark.skip(reason="needs network; run with -m live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture(scope="session")
def sut(request):
    backend = make_backend(request.config.getoption("--sut"))
    s = Sut(backend)
    yield s
    s.close()


def load_corpus(relpath):
    """Load a corpus file, or fail the collection with a useful message."""
    path = os.path.join(CORPUS, relpath)
    if not os.path.exists(path):
        raise RuntimeError(
            "missing corpus %s -- run: python3 harness/corpus/build_corpus.py"
            % relpath)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_golden(relpath):
    path = os.path.join(GOLDEN, relpath)
    if not os.path.exists(path):
        raise RuntimeError(
            "missing golden %s -- run: harness/oracle/run.sh generate"
            % relpath)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_golden_text(relpath):
    """Load a golden that is a real file (a .tex document) rather than JSON."""
    path = os.path.join(GOLDEN, relpath)
    if not os.path.exists(path):
        raise RuntimeError(
            "missing golden %s -- run: harness/oracle/run.sh generate" % relpath)
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def paired(corpus_rel, golden_rel=None):
    """Zip a corpus file with its golden into pytest.param() triples.

    Returns (id, case, expected) tuples. A case with no golden is an error, not
    a skip: it means the goldens are stale.
    """
    golden_rel = golden_rel or corpus_rel
    cases = load_corpus(corpus_rel)
    golden = {g["name"]: g for g in load_golden(golden_rel)}
    out = []
    for c in cases:
        if c["name"] not in golden:
            raise RuntimeError(
                "corpus case %r in %s has no golden in %s -- regenerate with "
                "harness/oracle/run.sh generate" % (c["name"], corpus_rel, golden_rel))
        out.append(pytest.param(c, golden[c["name"]], id=c["name"]))
    return out


def assert_matches(sut_call, expected, case):
    """Compare a SUT invocation against a golden that may be a value or a raise.

    `case['why']` is surfaced in the failure message so a red test explains what
    behavior just changed instead of only showing two strings.
    """
    why = case.get("why", "")
    if expected["ok"]:
        try:
            got = sut_call()
        except Exception as exc:
            pytest.fail(
                "expected %r but the SUT raised %s: %s\n  case: %s\n  why: %s"
                % (expected["result"], type(exc).__name__, exc,
                   case["name"], why))
        assert got == expected["result"], (
            "\n  case: %s\n  why:  %s\n  expected: %r\n  actual:   %r"
            % (case["name"], why, expected["result"], got))
    else:
        with pytest.raises(Exception) as ei:
            sut_call()
        got_type = getattr(ei.value, "type_name", type(ei.value).__name__)
        assert got_type == expected["error"]["type"], (
            "\n  case: %s\n  why:  %s\n  expected %s, got %s: %s"
            % (case["name"], why, expected["error"]["type"], got_type, ei.value))

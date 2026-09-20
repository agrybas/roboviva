"""Parity tests for the command-line scripts.

make_latex.py and make_pdf.py are thin drivers over the same library the web
app uses -- fetch, render, emit. They are genuinely run as subprocesses here so
argv handling, exit codes and stdout format are measured the way a user sees
them.

Neither uses argparse; both hand-roll `if len(argv) != 2`.
"""
import pytest

from conftest import assert_matches, load_golden, paired


def _cli(name):
    for g in load_golden("cli/scripts.json"):
        if g["name"] == name:
            assert g["ok"], g
            return g["result"]
    raise AssertionError("no golden named %r" % name)


@pytest.mark.parametrize("case,expected", paired("cli/scripts.json"))
def test_cli_invocation(sut, case, expected):
    """Full stdout / exit-code / created-files parity."""
    assert_matches(
        lambda: sut.cli(case["script_name"], case["argv"], case["script"]),
        expected, case)


@pytest.mark.parametrize("name", ["make_latex_no_args", "make_latex_too_many_args",
                                  "make_pdf_no_args"])
def test_wrong_argument_count_prints_usage_and_exits_1(name):
    """Both scripts guard on argc and return 1 (make_latex.py:23-25).

    The usage line interpolates argv[0], so it echoes back whatever path was
    used to invoke the script.
    """
    r = _cli(name)
    assert r["returncode"] == 1
    assert r["stdout"].startswith("Usage:")
    assert "route_id" in r["stdout"]


def test_non_numeric_route_id_is_an_uncaught_traceback():
    """`int(argv[1])` is unguarded (make_latex.py:27).

    A user typo produces a Python traceback on stderr rather than the usage
    message -- the argc guard is the only input validation either script has.
    """
    r = _cli("make_latex_non_numeric")
    assert r["returncode"] == 1
    assert r["stdout"] == "", "nothing on stdout, only the traceback"
    assert any("ValueError" in line for line in r["stderr_tail"]), r["stderr_tail"]


def test_make_latex_prefixes_progress_with_latex_comments():
    """stdout is not pure LaTeX -- but it is still valid LaTeX.

    make_latex.py:28-30 prints progress through the SAME stream as the
    document, and escapes it as '%' comments so that

        python2 make_latex.py 123 | pdflatex

    still compiles. make_pdf.py, which writes to a terminal rather than a pipe,
    does not bother.
    """
    out = _cli("make_latex_happy")["stdout"]
    first_line = out.splitlines()[0]
    assert first_line.startswith("%"), first_line
    assert "Downloading route from ridewithgps" in first_line
    assert "Done [etag:" in first_line, "trailing comma keeps it on one line"


def test_make_latex_emits_the_document_on_stdout():
    """The LaTeX document follows the progress comments."""
    out = _cli("make_latex_happy")["stdout"]
    assert r"\documentclass[11pt]{article}" in out
    assert out.rstrip().endswith(r"\end{document}")


def test_make_latex_exits_zero_on_success():
    """main() falls off the end returning None, so sys.exit(None) -> 0."""
    assert _cli("make_latex_happy")["returncode"] == 0


def test_make_pdf_writes_route_id_pdf_into_the_cwd():
    """make_pdf.py:34-37 writes '<route_id>.pdf' relative to the working dir.

    No output-path option and no overwrite check -- running it twice silently
    replaces the previous file.
    """
    r = _cli("make_pdf_happy")
    assert r["returncode"] == 0
    assert r["files_created"] == ["123.pdf"]


def test_make_pdf_progress_is_not_comment_escaped():
    """Unlike make_latex.py, make_pdf.py prints plain progress text.

    Consistent with its output going to a file rather than through the pipe.
    """
    out = _cli("make_pdf_happy")["stdout"]
    assert out.startswith("Downloading route from ridewithgps"), out
    assert not out.startswith("%")
    for stage in ("Generating latex", "Rendering PDF to '123.pdf'"):
        assert stage in out, out


def test_cli_uses_the_json_api_not_the_csv_one():
    """Both scripts call getETagAndCuesheet_viaJSON (make_latex.py:29).

    So they inherit the JSON path's route name, elevation and
    AdjustStartAndEnd handling -- and its dependence on api_key being present
    in the URL. Nothing in the repo calls the CSV variant at all.
    """
    out = _cli("make_latex_happy")["stdout"]
    assert "etag:" in out, "an etag came back, so the fetch path ran"

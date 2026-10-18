"""Parity tests for whole LaTeX documents (latex.makeLatex, latex.py:139-241).

The generated .tex is the byte-exact contract for the whole renderer: preamble,
headers, table setup, every row, footer. Goldens live as real .tex files under
harness/golden/latex/documents/ so a diff is readable as LaTeX and can be
compiled by hand when something looks wrong.
"""
import pytest

from conftest import load_corpus, load_golden, load_golden_text


def _index():
    return {g["name"]: g for g in load_golden("latex/documents.json")}


def _cases():
    idx = _index()
    out = []
    for c in load_corpus("latex/documents.json"):
        if c["name"] not in idx:
            raise RuntimeError(
                "document case %r has no golden -- run "
                "harness/oracle/run.sh generate" % c["name"])
        out.append(pytest.param(c, idx[c["name"]], id=c["name"]))
    return out


@pytest.mark.parametrize("case,expected", _cases())
def test_document_matches_golden(sut, case, expected):
    """Byte-exact whole-document parity."""
    if not expected["ok"]:
        with pytest.raises(Exception) as ei:
            sut.make_latex(case["route"])
        got = getattr(ei.value, "type_name", type(ei.value).__name__)
        assert got == expected["error"]["type"], (
            "case %s (%s): expected %s, got %s"
            % (case["name"], case["why"], expected["error"]["type"], got))
        return

    golden = load_golden_text(expected["file"])
    actual = sut.make_latex(case["route"])
    assert actual == golden, (
        "document %r differs from the golden.\n  why: %s\n"
        "  compare: diff <(...) harness/golden/%s"
        % (case["name"], case["why"], expected["file"]))


def _doc(name):
    return load_golden_text(_index()[name]["file"])


def test_preamble_package_set_is_fixed():
    """The preamble is a fixed string (latex.py:167-182).

    Every package here is a hard runtime dependency on the host TeX
    installation, which is why the README requires pdflatex plus Helvetica.
    A rewrite that changes rendering backend has to replace all of it.
    """
    doc = _doc("minimal")
    for pkg in ["geometry", "colortbl", "supertabular", "amsmath", "helvet",
                "fourier", "bbding", "fancyhdr", "lastpage"]:
        assert r"\usepackage" in doc and pkg in doc, "missing %s" % pkg
    assert r"\usepackage[alpine]{ifsym}" in doc, "ifsym provides \\Mountain"


def test_page_geometry_and_two_column_layout():
    """Letter paper, narrow margins, two columns (latex.py:169-170, 218).

    A cue sheet is meant to be folded and clipped to a handlebar bag, which is
    what the 0.20in side margins and two-column flow are for.
    """
    doc = _doc("minimal")
    assert ("[left=0.20in,right=0.20in,top=0.7in,bottom=0.25in]{geometry}"
            in doc)
    assert r"\geometry{letterpaper}" in doc
    assert r"\twocolumn" in doc


def test_column_headers_are_go_at_on_for():
    """The four-column vocabulary (latex.py:219-227).

    Go = the instruction, At = distance from start, On = street/description,
    For = distance until the next cue. Standard randonneuring cue sheet layout.
    """
    doc = _doc("minimal")
    for col in ("Go", "At", "On", "For"):
        assert r"\textbf{\textcolor{white}{%s}}" % col in doc
    assert r"\begin{supertabular}{|c|p{0.30in}|p{2.25in}|l|}" in doc


def test_named_route_puts_stats_in_the_left_header():
    """With a title, distance and climb join it on the left (latex.py:195-196)."""
    assert (r"\lhead{\small \emph{Test Route (1.0 mi / 1000 ft)}}"
            in _doc("named_route"))
    assert r"\rhead{\small \emph{Route \#42}}" in _doc("named_route")


def test_unnamed_route_moves_stats_to_the_right_header():
    """With no title there is nothing to attach the stats to, so they follow
    the route number instead (latex.py:197-199)."""
    assert r"\rhead{\small \emph{Route \#1} \emph{(1.0 mi)}}" in _doc("minimal")
    assert r"\lhead" not in _doc("minimal")


def test_zero_climb_is_indistinguishable_from_unknown_climb():
    """`if elevation_gain_ft:` is falsy for 0 (latex.py:190).

    A genuinely flat route and a route whose climb was never computed produce
    identical headers. Minor, but it is a real information loss and a rewrite
    using `is not None` would change user-visible output.
    """
    flat = _doc("zero_elevation")
    unknown = _doc("no_elevation")
    assert "(12.3 mi)" in flat and "(12.3 mi)" in unknown
    assert "ft" not in flat.split(r"\lhead")[1].split("}")[0]


def test_climb_is_truncated_not_rounded():
    """'%d' truncates, so 999.9ft prints as 999 (latex.py:191)."""
    assert "(12.3 mi / 999 ft)" in _doc("elevation_truncated")


def test_route_name_is_escaped():
    """Route names are user-controlled and reach \\lhead (latex.py:196)."""
    doc = _doc("name_with_latex_specials")
    assert r"\textbackslash terrible" in doc
    assert r"\&oute" in doc
    assert r"\%\%\%" in doc


def test_emphasis_does_not_work_in_route_names():
    """QUIRK: _makeHeader escapes the name but never calls _format.

    So '**bold**' in a route title renders as literal asterisks, even though
    the same markup works inside cue descriptions and notes. tips.html
    advertises emphasis without mentioning it stops at the header.
    """
    assert "A **bold** title" in _doc("name_with_emphasis")
    assert r"\textbf{bold}" not in _doc("name_with_emphasis")


def test_string_route_id_raises():
    """_makeHeader does '%d' % route_id (latex.py:186), so a str id is fatal.

    ridewithgps stores whatever route_id it was handed without coercion, and
    the in-repo tests assert route.id is a STRING -- so the two halves of the
    codebase disagree about the type. The Flask layer papers over it because
    its <int:route_id> converter guarantees an int.
    """
    idx = _index()["string_route_id"]
    assert not idx["ok"]
    assert idx["error"]["type"] == "TypeError"


def test_empty_route_still_produces_a_valid_document():
    """Zero entries -> an empty but well-formed table."""
    doc = _doc("empty_route")
    assert r"\begin{supertabular}" in doc and r"\end{supertabular}" in doc
    assert r"\end{document}" in doc


def test_footer_is_page_x_of_y():
    """\\pageref{LastPage} needs the lastpage package and two pdflatex passes.

    This is why tex.convert re-runs until texput.aux stabilizes (tex.py:151-158)
    rather than compiling once.
    """
    assert (r"\fancyfoot[C]{\footnotesize{\emph{Page~\thepage~of~\pageref{LastPage}}}}"
            in _doc("minimal"))


def test_multipage_document_has_all_rows():
    """120 entries all reach the document (latex.py:150-151)."""
    doc = _doc("multipage")
    assert doc.count(r"\\ \hline") >= 120
    assert "Street number 119" in doc


def test_unicode_passes_through_to_the_tex_source():
    """Non-ASCII is not escaped -- it is written as UTF-8 into the .tex.

    tex.convert encodes the source as UTF-8 (tex.py:127); whether pdflatex can
    then find a glyph is a separate question, covered by the PDF tests.
    """
    assert "Rue de l'Église" in _doc("unicode_latin")
    assert "ポケモンマンホール巡り200" in _doc("unicode_cjk")
    assert "Φθινοπωρινός" in _doc("unicode_greek_name")


def test_document_ends_with_the_fixed_footer():
    """LatexFooter is a module constant (latex.py:237-241)."""
    assert _doc("minimal").endswith(
        "\n\\end{supertabular}\n\\end{center}\n\\end{document}\n")

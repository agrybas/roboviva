#!/usr/bin/env python3
"""Generate the LaTeX rendering corpus: single rows and whole documents.

The generated .tex is the byte-exact parity contract. PDFs are compared by
summary because they are not byte-reproducible, but the LaTeX that produces
them is, so this is where a rendering regression actually gets caught.

    python3 harness/corpus/build_latex_corpus.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

ZWSP = "​"


def case(name, why, **payload):
    d = {"name": name, "why": why}
    d.update(payload)
    return d


def entry(instruction="", description="", absolute_distance=0.0, note="",
          modifier="", for_distance=None, color="None"):
    return {"instruction": instruction, "description": description,
            "absolute_distance": absolute_distance, "note": note,
            "modifier": modifier, "for_distance": for_distance, "color": color}


def route(entries, length_mi=10.0, route_id=123, name=None,
          elevation_gain_ft=None):
    return {"entries": entries, "length_mi": length_mi, "id": route_id,
            "name": name, "elevation_gain_ft": elevation_gain_ft}


# ---------------------------------------------------------------------------
# latex._entryToLatex -- one supertabular row  (latex.py:104-137)
# ---------------------------------------------------------------------------
ENTRY_ROWS = [
    case("minimal", "Empty everything -- the degenerate row.", entry=entry()),

    case("plain_right", "The common case: a turn with a street name.",
         entry=entry("R", "Foo St.", 1.0, for_distance=2.0, color="Gray")),

    case("with_note",
         "A note is appended as ' \\newline \\textit{...}' (latex.py:125). "
         "Note latex_tests.py:139 still expects '\\textbf{Note:} \\emph{...}' "
         "-- that test is stale (commit 69ee4d1 'cleaner notes').",
         entry=entry("R", "Foo St.", 1.0, note="watch for gravel",
                     for_distance=2.0)),

    case("note_without_description",
         "When the description is blank the note REPLACES it rather than being "
         "appended (latex.py:121-123), so a note-only cue still fills the On "
         "column.", entry=entry("", "", 1.0, note="Regroup here")),

    case("whitespace_only_description",
         "The check is `esc_description.strip() == ''`, so a description of "
         "spaces also promotes the note.",
         entry=entry("", "   ", 1.0, note="Regroup here")),

    case("for_distance_zero",
         "A for_distance of exactly 0.0 is falsy, so the For column is EMPTY "
         "rather than '  0.0' (latex.py:126).",
         entry=entry("R", "Foo", 1.0, for_distance=0.0)),

    case("for_distance_none", "No for_distance -- the last row of a sheet.",
         entry=entry("R", "Foo", 1.0, for_distance=None)),

    case("for_distance_rounding",
         "The For column is '%5.1f', so sub-0.05 legs round to 0.0 while still "
         "being truthy.", entry=entry("R", "Foo", 1.0, for_distance=0.04)),

    case("distance_width",
         "The At column is '%5.1f'; a 3-digit distance consumes the padding.",
         entry=entry("R", "Foo", 123.4, for_distance=1.0)),

    case("yellow_row", "Danger and pit stops get a yellow \\rowcolor.",
         entry=entry("!", "Gravel section", 1.0, for_distance=1.0,
                     color="Yellow")),

    case("gray_row", "Right turns (and, via the missing-comma quirk, every "
         "Start/End/Generic row) get [gray]{0.8}.",
         entry=entry("R", "Foo", 1.0, for_distance=1.0, color="Gray")),

    case("modifier_quick", "QUICK + RIGHT concatenates to 'QR'.",
         entry=entry("R", "Foo", 1.0, modifier="Q", for_distance=1.0)),

    case("modifier_slight", "SLIGHT + LEFT concatenates to 'BL'.",
         entry=entry("L", "Foo", 1.0, modifier="B", for_distance=1.0)),

    case("climb_glyph", "Climb categories render as a mountain glyph.",
         entry=entry("C1", "Big climb", 1.0, for_distance=1.0)),

    case("summit_glyph", "Summit shares the glyph with the label 'End'.",
         entry=entry("^", "Top", 1.0, for_distance=1.0)),

    case("first_aid_glyph", "First aid renders as a raised plus.",
         entry=entry("+", "Clinic", 1.0, for_distance=1.0)),

    case("escaping_in_description",
         "User text reaching the renderer: every LaTeX special must be "
         "neutralized before it hits pdflatex.",
         entry=entry("R", r"# & $ _ | < > { } \cmd %", 1.0, for_distance=1.0)),

    case("emphasis_in_description",
         "Markdown-ish emphasis survives escaping and becomes real LaTeX.",
         entry=entry("R", "Turn at the **big** red *barn*", 1.0,
                     for_distance=1.0)),

    case("emphasis_in_note", "_format is applied to the note too (latex.py:130).",
         entry=entry("R", "Foo", 1.0, note="**Do not** miss this",
                     for_distance=1.0)),

    case("ampersand_would_break_the_table",
         "A raw '&' is a column separator; unescaped it would corrupt the row.",
         entry=entry("R", "Smith & Wesson Ave", 1.0, for_distance=1.0)),

    case("percent_would_comment_the_row",
         "A raw '%' would comment out the rest of the line, silently dropping "
         "the For column.", entry=entry("R", "50% grade", 1.0, for_distance=1.0)),

    case("zwsp_in_description",
         "RideWithGPS emits U+200B between joined street names; commit 2278d0d.",
         entry=entry("R", "Richardsville Rd/" + ZWSP + "Sagamore Rd", 1.0,
                     for_distance=1.0)),

    case("unicode_description", "Accented Latin text.",
         entry=entry("R", "Rue de l'Église", 1.0, for_distance=1.0)),

    case("custom_instruction",
         "A [tag]-derived instruction renders bold in the Go column.",
         entry=entry("U-Turn", "Head back", 1.0, for_distance=1.0)),

    case("custom_instruction_with_specials",
         "The tag is user-controlled, so it is escaped like any other input.",
         entry=entry("R&D", "Foo", 1.0, for_distance=1.0)),

    case("unmapped_uturn",
         "How route 55132669's 'Uturn' type actually reaches the page.",
         entry=entry("Uturn", "U-Turn to return", 1.0, for_distance=1.0)),
]

# ---------------------------------------------------------------------------
# latex.makeLatex -- whole documents  (latex.py:139-241)
# ---------------------------------------------------------------------------
_TWO = [entry("", "Start of route", 0.0, for_distance=1.0, color="Gray"),
        entry("R", "Foo St.", 1.0, color="Gray")]

DOCUMENTS = [
    case("minimal",
         "One entry, no name, no elevation. The stats land in the RIGHT header "
         "because there is no title to attach them to (latex.py:195-199).",
         route=route([entry("L", "Foo", 0.0)], length_mi=1.0, route_id=1)),

    case("named_route",
         "With a name, stats move to the LEFT header alongside the title.",
         route=route(_TWO, length_mi=1.0, route_id=42, name="Test Route",
                     elevation_gain_ft=1000.0)),

    case("no_elevation",
         "elevation_gain_ft of None -> the header shows miles only.",
         route=route(_TWO, length_mi=12.3, route_id=42, name="No Climb")),

    case("zero_elevation",
         "0 is falsy, so a genuinely flat route also shows miles only -- a "
         "flat route and an unknown-climb route are indistinguishable.",
         route=route(_TWO, length_mi=12.3, route_id=42, name="Flat",
                     elevation_gain_ft=0.0)),

    case("elevation_truncated",
         "Climb is '%d' so it truncates rather than rounds: 999.9ft -> 999.",
         route=route(_TWO, length_mi=12.3, route_id=42, name="Climby",
                     elevation_gain_ft=999.9)),

    case("name_with_latex_specials",
         "Route names are user-controlled and reach \\lhead, so they are "
         "escaped (latex.py:196).",
         route=route(_TWO, length_mi=1.0, route_id=42,
                     name=r"\terrible &oute Name \\ %%%",
                     elevation_gain_ft=123.45)),

    case("name_with_emphasis",
         "IMPORTANT: _makeHeader escapes the name but never calls _format, so "
         "'**bold**' in a route title stays literal asterisks -- emphasis works "
         "in cue rows but NOT in the header.",
         route=route(_TWO, length_mi=1.0, route_id=42,
                     name="A **bold** title", elevation_gain_ft=100.0)),

    case("string_route_id",
         "_makeHeader does '%d' % route_id (latex.py:186), so a string id "
         "raises TypeError -- yet ridewithgps stores whatever it was given and "
         "the old tests assert route.id is a STRING. Recording the failure.",
         route=route(_TWO, length_mi=1.0, route_id="6260667", name="Str Id")),

    case("all_instruction_glyphs",
         "Every Instruction value in one document, so each glyph is exercised. "
         "Descriptions are deliberately plain: an earlier version used the "
         "instruction itself as the description text, which put a bare '^' in "
         "a cell and killed the render for reasons unrelated to the glyphs. "
         "See caret_in_description.",
         route=route(
             [entry(i, "Point number %d" % n, float(n), for_distance=1.0)
              for n, i in enumerate(["L", "R", "S", "PIT", "!", "X", "CHC",
                                     "C1", "C2", "C3", "C4", "C5", "^", "+",
                                     ""])],
             length_mi=15.0, route_id=7, name="Glyph Sampler",
             elevation_gain_ft=500.0)),

    case("caret_in_description",
         "BUG: a bare '^' in a description is FATAL to the whole PDF. "
         "_escape (latex.py:48-63) covers # & $ _ | < > % { } and U+200B but "
         "NOT '^', which LaTeX reads as a superscript operator outside math "
         "mode -> 'Missing $ inserted' -> no output file at all. A rider who "
         "types '85^ cadence' or 'bear ^ the bridge' in RideWithGPS gets the "
         "0xFF error page and no explanation. One cue poisons the entire sheet.",
         route=route([entry("R", "Point ^", 0.0, for_distance=1.0)],
                     length_mi=1.0, route_id=15, name="Caret")),

    case("tilde_in_description",
         "'~' is also unescaped, but it is a non-breaking space in LaTeX "
         "rather than a syntax error, so this one renders -- silently wrong "
         "instead of loudly broken.",
         route=route([entry("R", "Point ~ here", 0.0, for_distance=1.0)],
                     length_mi=1.0, route_id=16, name="Tilde")),

    case("unescaped_specials_survey",
         "The other characters _escape does not handle: [ ] \" and a backtick. "
         "None are fatal, but '`' becomes a left quote and '\"' becomes a "
         "double quote, so the rendered text differs from what was typed.",
         route=route([entry("R", "A [b] \"c\" `d`", 0.0, for_distance=1.0)],
                     length_mi=1.0, route_id=17, name="Unescaped")),

    case("all_row_colours",
         "One row of each colour, to pin the \\rowcolor arguments in context.",
         route=route([entry("R", "Gray", 0.0, for_distance=1.0, color="Gray"),
                      entry("!", "Yellow", 1.0, for_distance=1.0,
                            color="Yellow"),
                      entry("L", "None", 2.0, color="None")],
                     length_mi=3.0, route_id=8, name="Colours")),

    case("empty_route",
         "No entries at all: a valid document with an empty table. Reachable "
         "only via the CSV path, since the JSON path always synthesizes "
         "sentinels.",
         route=route([], length_mi=0.0, route_id=9, name="Empty")),

    case("multipage",
         "120 rows, enough to spill past one page and exercise \\pageref"
         "{LastPage} and the two-column supertabular flow.",
         route=route([entry("R" if n % 2 else "L", "Street number %d" % n,
                            n * 0.5, for_distance=0.5,
                            color="Gray" if n % 2 else "None")
                      for n in range(120)],
                     length_mi=60.0, route_id=10, name="Long Route",
                     elevation_gain_ft=5000.0)),

    case("notes_heavy",
         "Long notes wrapping inside a 2.25in column.",
         route=route([entry("R", "Foo St.", 0.0,
                            note="A rather long note that will certainly need "
                                 "to wrap across several lines in the On "
                                 "column of the rendered sheet",
                            for_distance=1.0),
                      entry("", "", 1.0, note="Note-only row")],
                     length_mi=2.0, route_id=11, name="Notes")),

    case("unicode_latin",
         "Accented Latin renders fine with Helvetica.",
         route=route([entry("R", "Rue de l'Église", 0.0, for_distance=1.0),
                      entry("L", "Straße", 1.0)],
                     length_mi=2.0, route_id=12, name="Café Ride")),

    case("unicode_greek_name",
         "Greek in the route name. pdflatex with Helvetica has no glyphs for "
         "this; whether it warns or hard-fails is recorded, not assumed.",
         route=route(_TWO, length_mi=1.0, route_id=13,
                     name="Mini Brevet-Φθινοπωρινός Χολωμόντας")),

    case("unicode_cjk",
         "Japanese in both name and body -- same font-stack question.",
         route=route([entry("R", "Uターンして", 0.0, for_distance=1.0)],
                     length_mi=1.0, route_id=14,
                     name="ポケモンマンホール巡り200")),
]

WRITERS = [
    ("latex/entry_rows.json", ENTRY_ROWS),
    ("latex/documents.json", DOCUMENTS),
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

#!/usr/bin/env python3
"""Generate the corpus of INPUT cases.

Inputs only -- expected outputs come from running the legacy code
(harness/oracle/generate.py). Keeping the two apart is what makes the goldens
observed behavior rather than someone's reading of the source.

    python3 harness/corpus/build_corpus.py

Cases are plain JSON so both the py2 oracle and the py3 suite consume the same
bytes. Each carries a `why` string; if a case cannot say what it pins, it does
not belong here.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

ZWSP = "​"


def case(name, why, **payload):
    d = {"name": name, "why": why}
    d.update(payload)
    return d


# ---------------------------------------------------------------------------
# latex._escape  (latex.py:48-63)
# ---------------------------------------------------------------------------
ESCAPE = [
    case("empty", "Degenerate input.", text=""),
    case("plain", "No special characters -- must pass through untouched.",
         text="Main St"),

    # Each special character alone.
    case("backslash_single", "The leading rule re.sub(r'\\\\([^\\\\]?)') "
         "consumes the char after the backslash.", text="\\"),
    case("backslash_command", "A LaTeX-looking command must be neutralized.",
         text="\\testcommand"),
    case("backslash_double", "Two backslashes: the [^\\\\] class means the "
         "first rule does not pair them.", text="\\\\"),
    case("underscore", "-> \\textunderscore with a trailing space.", text="_"),
    case("dollar", "-> \\$", text="$"),
    case("hash", "-> \\#", text="#"),
    case("ampersand", "-> \\& ; would otherwise be a tabular column break.",
         text="&"),
    case("pipe", "-> $|$ (math mode, not an escape).", text="|"),
    case("less_than", "-> $<$", text="<"),
    case("greater_than", "-> $\\Rightarrow$ -- an ARROW, not a literal '>'. "
         "Asymmetric with '<' and almost certainly deliberate: cue sheets "
         "write 'A > B' to mean 'A leads to B'.", text=">"),
    case("percent", "-> \\% ; would otherwise comment out the rest of the row.",
         text="%"),
    case("brace_open", "-> \\{", text="{"),
    case("brace_close", "-> \\}", text="}"),
    case("zwsp", "U+200B -> \\hspace{0pt}. This rule runs LAST, so the braces "
         "it introduces are not themselves escaped. Commit 2278d0d.",
         text="a" + ZWSP + "b"),

    # Characters that are NOT escaped -- pinning the absence of a rule.
    case("tilde_not_escaped", "'~' is a LaTeX non-breaking space and is NOT "
         "escaped. Latent rendering bug, frozen as-is.", text="~"),
    case("caret_not_escaped", "'^' is superscript in math mode and is NOT "
         "escaped.", text="^"),
    case("brackets_not_escaped", "'[' and ']' are NOT escaped.", text="[x]"),
    case("quote_not_escaped", "'\"' is NOT escaped.", text='say "hi"'),
    case("backtick_not_escaped", "'`' is NOT escaped.", text="`"),

    # Ordering interactions -- the backslash rule runs first.
    case("backslash_then_amp", "'\\&' exercises rule order: backslash first, "
         "then '&'.", text="\\&"),
    case("all_specials", "The kitchen sink, matching latex_tests.py:97.",
         text=r'# & $ _ | < > { } \testcommand \\ %'),
    case("real_street_zwsp", "Verbatim from route 47438923: RWGPS joins "
         "street names with a zero-width space.",
         text="Richardsville Rd/" + ZWSP + "Sagamore Rd"),
    case("real_amp_street", "Verbatim shape from route 47438923.",
         text="Smith & Wesson Ave"),
]

# ---------------------------------------------------------------------------
# latex._format  (latex.py:65-90)
# The 25 pairs below are the table at latex_tests.py:191-218, which I verified
# still matches the current implementation. They are the single best
# ready-made behavioral spec in the repo.
# ---------------------------------------------------------------------------
_FORMAT_FROM_LEGACY_TESTS = [
    ("basic_emph", "*foo*"),
    ("basic_strong", "**foo**"),
    ("strong_internal", "foo**bar**baz"),
    ("emph_internal", "foo*bar*baz"),
    ("emph_noclose", "*foobar"),
    ("strong_noclose", "**foobar"),
    ("emph_unbalanced", "**foobar*"),
    ("emph_unbalanced2", "*foobar**"),
    ("emph_strong_together", "***foobar***"),
    ("star_with_escape", "**foo \\* bar \\* baz**"),
    ("star_with_space", "**foo * bar * baz**"),
    ("strong_in_emph", "***strong** in emph*"),
    ("emph_in_strong", "***emph* in strong**"),
    ("emph_in_strong_internal", "**foo *bar* baz**"),
    ("strong_in_emph_internal", "*foo **bar** baz*"),
    ("in_emph_strong", "*in emph **strong***"),
    ("in_strong_emph", "**in strong *emph***"),
    ("odd_nestings", "*bar *baz**"),
    ("odd_nestings2", "**bar* baz*"),
    ("pathological_nesting", "**foo**bar**baz**"),
    ("delimiter_closing", "*foo**bar***"),
    ("mismatches1", "*bar***"),
    ("mismatches2", "***foo*"),
    ("mismatches3", "***bar**"),
    ("mismatches4", "**bar***"),
    ("mismatches5", "***foo *bar*"),
]

FORMAT = [
    case("legacy_" + n,
         "From the table at latex_tests.py:191-218 -- the repo's own spec for "
         "the emphasis parser.", text=t)
    for n, t in _FORMAT_FROM_LEGACY_TESTS
] + [
    case("empty", "Degenerate input.", text=""),
    case("no_markup", "Plain text must be untouched.", text="Main St"),
    case("single_star", "One bare star, nothing to pair with.", text="*"),
    case("double_star", "Two bare stars.", text="**"),
    case("triple_star", "Three bare stars.", text="***"),
    case("star_space_only", "Whitespace-delimited star is protected by the "
         "step-0 rule at latex.py:70.", text="a * b"),
    case("doublestar_space_only", "Whitespace-delimited '**', latex.py:71.",
         text="a ** b"),
    case("escaped_underscore", "The final rule un-escapes \\_ as well as \\*.",
         text=r"foo\_bar"),
    case("after_escape_backslash", "_format runs AFTER _escape, so it sees "
         "\\textbackslash already present. Pins that the emphasis regexes do "
         "not corrupt escape output.", text=r"\textbackslash foo *bar*"),
    case("after_escape_underscore", "Likewise for \\textunderscore.",
         text=r"a\textunderscore b **c**"),
    case("emph_with_escaped_specials", "Emphasis wrapping already-escaped "
         "text -- the realistic composition.", text=r"**\$5 toll**"),
]

# ---------------------------------------------------------------------------
# ridewithgps._cleanDescription  (ridewithgps.py:252-261)
# Ten ordered re.sub calls. Order is load-bearing.
# ---------------------------------------------------------------------------
CLEAN_DESCRIPTION = [
    case("empty", "Degenerate input.", description=""),
    case("plain", "Nothing matches -- passes through.", description="Main St"),

    # Rule 1: strip a leading [tag].
    case("tag_stripped", "Rule 1 removes the custom-instruction tag.",
         description="[L/QR] Foo Bar"),
    case("tag_with_leading_space", "Leading whitespace is allowed.",
         description="   [U] Foo"),
    case("tag_empty_not_stripped", "'[]' has no content, so [^\\]]+ fails.",
         description="[] Foo"),
    case("tag_midstring_kept", "Rule 1 is anchored; a mid-string tag stays.",
         description="Foo [Rough] Bar"),

    # Rule 2: traffic circle.
    case("traffic_circle", "-> '@ Circle,'", description="At the traffic circle, foo"),
    case("traffic_circle_case", "Case-insensitive.",
         description="AT THE TRAFFIC CIRCLE, foo"),

    # Rules 3-10: turn prefixes.
    case("slight_left_toward", "Rule 3.", description="Slight left toward foo"),
    case("slight_right_onto", "Rule 3.", description="Slight right onto foo"),
    case("bear_left_on", "Rule 3.", description="Bear left on foo"),
    case("keep_right_toward", "Rule 3.", description="Keep right toward foo"),
    case("keep_right_on_caps", "Rule 3, case-insensitive.",
         description="keep RIGHT ON foo"),
    case("turn_left_onto", "Rule 3 -- the single most common RWGPS string.",
         description="Turn left onto foo"),
    case("bear_right_to_stay_on", "Rule 4 -> 'TRO foo'.",
         description="Bear right to stay on foo"),
    case("bear_right_to_remain_on", "Rules 4+6 -> 'TRO foo'.",
         description="Bear right to remain on foo"),
    case("mid_to_stay_on", "Rule 5 is unanchored and rewrites mid-string.",
         description="Turn left onto Bar to stay on Baz"),
    case("turn_left_bare", "Rule 7, no preposition.", description="Turn left foo"),
    case("left_onto", "Rule 8, no leading verb.", description="Left onto foo"),
    case("continue_onto", "Rule 9.", description="Continue onto foo"),
    case("continue_straight_onto", "Rule 10.",
         description="Continue straight onto foo"),
    case("continue_straight_on", "Rule 10.",
         description="Continue straight on foo"),

    # The gap: "Sharp" is missing from every alternation.
    case("sharp_left_NOT_stripped",
         "'Sharp left onto Foo' is UNCHANGED -- 'Sharp' is absent from the "
         "alternations at ridewithgps.py:254,255,258 even though 'Sharp Left' "
         "is a recognized instruction type (:268). Real routes hit this: "
         "47438923 has Sharp Left/Sharp Right points.",
         description="Sharp left onto Foo"),
    case("sharp_right_NOT_stripped", "Same gap, right side.",
         description="Sharp right onto Foo"),

    # Real-world strings from the approval fixtures.
    case("real_uturn", "From route 55132669 (type 'Uturn', unmapped).",
         description="U-Turn to return from Millbrook Mountain Carriage Road"),
    case("real_keep_right", "From route 56819245, where the type is the "
         "lowercase string 'right'.", description="Keep right"),
    case("real_zwsp_street", "From route 47438923.",
         description="Turn right onto Richardsville Rd/" + ZWSP + "Sagamore Rd"),
]

# ---------------------------------------------------------------------------
# ridewithgps._parseCustomInstruction  (ridewithgps.py:367)
# ---------------------------------------------------------------------------
PARSE_CUSTOM = [
    case("empty", "Degenerate input.", description=""),
    case("common", "The documented form (tips.html).", description="[L/QR] Foo Bar"),
    case("leading_whitespace", "Allowed by ^\\s*.", description="   [L/QR] Foo Bar"),
    case("empty_brackets", "[^\\]]+ requires >=1 char -> None.", description="[] Foo Bar"),
    case("not_at_start", "Anchored -> None.", description="Foo [L] Bar"),
    case("second_bracket_ignored", "Character class is not greedy across ']'.",
         description="[L/QR] Foo [Rough]"),
    case("start_tag", "Feeds cue_utils.AdjustStartAndEnd.", description="[start] Real start"),
    case("end_tag_capitalized", "Route 6260667 uses '[End]'; the comparison at "
         "cue_utils.py:28 lowercases, so case does not matter there.",
         description="[End] Custom end entry"),
    case("tag_only", "No trailing text.", description="[U]"),
    case("nested_brackets", "Inner ']' terminates the match.", description="[a[b]c] Foo"),
    case("spaces_in_tag", "Route 6260667 uses '[Custom Instruction]'.",
         description="[Custom Instruction] Foo"),
    case("latex_special_in_tag", "The tag becomes the instruction and is "
         "escaped downstream by _instructionToLatex.", description="[R&D] Foo"),
]

# ---------------------------------------------------------------------------
# ridewithgps._instructionStrToCueInstruction  (ridewithgps.py:264-296)
# ---------------------------------------------------------------------------
_KNOWN = ["Left", "Slight Left", "Sharp Left", "Right", "Slight Right",
          "Sharp Right", "Straight", "Food", "Water", "Danger", "Start", "End",
          "Generic", "Control", "Summit", "4th Category", "3rd Category",
          "2nd Category", "1st Category", "Hors Category", "First Aid"]

INSTRUCTION_STR = [
    case("known_" + s.replace(" ", "_").lower(),
         "Mapped instruction string.", instruction_str=s)
    for s in _KNOWN
] + [
    case("empty", "Empty string falls through to passthrough.", instruction_str=""),
    case("unknown_custom", "Unrecognized -> returned verbatim (:294-296).",
         instruction_str="Test Instruction"),

    # Unmapped types found in real public routes today.
    case("real_uturn", "Route 55132669 and others. RWGPS emits 'Uturn'; there "
         "is no mapping, so it renders literally as \\textbf{Uturn}.",
         instruction_str="Uturn"),
    case("real_climb", "Route 55132669 emits 'Climb'. Unmapped.",
         instruction_str="Climb"),
    case("real_valley", "Route 55132669 emits 'Valley'. Unmapped.",
         instruction_str="Valley"),
    case("real_lowercase_right", "Route 56819245 emits lowercase 'right'. The "
         "mapping is case-SENSITIVE, so this is NOT Instruction.RIGHT -- it "
         "passes through as the literal string and loses its gray row colour.",
         instruction_str="right"),
    case("real_lowercase_left", "Route 56819245 emits lowercase 'left'.",
         instruction_str="left"),
    case("case_upper_left", "Case sensitivity, upper.", instruction_str="LEFT"),
    case("whitespace_padded", "No strip() anywhere -> passthrough.",
         instruction_str=" Left "),
]

# ---------------------------------------------------------------------------
# cue.ColorFromInstruction  (cue.py:47-56)
# ---------------------------------------------------------------------------
COLOR_FROM_INSTRUCTION = [
    case("left", "Instruction.LEFT -> no colour.", instruction="L"),
    case("right", "Instruction.RIGHT -> GRAY.", instruction="R"),
    case("straight", "-> no colour.", instruction="S"),
    case("pit", "Instruction.PIT -> YELLOW.", instruction="PIT"),
    case("danger", "Instruction.DANGER -> YELLOW.", instruction="!"),
    case("crosses", "Instruction.CROSSES; nothing ever produces it.",
         instruction="X"),
    case("cat_hc", "-> no colour.", instruction="CHC"),
    case("cat_1", "-> no colour.", instruction="C1"),
    case("cat_5", "-> no colour; nothing ever produces CAT_5.", instruction="C5"),
    case("summit", "-> no colour.", instruction="^"),
    case("first_aid", "-> no colour.", instruction="+"),
    case("none_empty_string",
         "THE BIG ONE. Instruction.NONE is the empty string, and cue.py:53 "
         "reads `instruction in (Instruction.RIGHT)` -- a missing comma makes "
         "that a SUBSTRING test against 'R', and '' is a substring of "
         "everything. So every Start/End/Generic/Control row comes out GRAY. "
         "Almost certainly a typo; frozen because the output depends on it.",
         instruction=""),
    case("custom_r_substring",
         "'R' as a custom instruction is also a substring of 'R' -> GRAY.",
         instruction="R"),
    case("custom_multi_char", "'QR' is NOT a substring of 'R' -> no colour.",
         instruction="QR"),
    case("custom_uturn", "Unmapped real-world type -> no colour.",
         instruction="Uturn"),
]

# ---------------------------------------------------------------------------
# latex._instructionToLatex  (latex.py:24-46)
# ---------------------------------------------------------------------------
_ALL_INSTRUCTIONS = ["L", "R", "S", "PIT", "!", "X", "CHC", "C1", "C2", "C3",
                     "C4", "C5", "^", "+", ""]
_ALL_MODIFIERS = ["", "B", "Q"]

INSTRUCTION_TO_LATEX = [
    case("i%s_m%s" % (i or "none", m or "none"),
         "Every Instruction x Modifier combination.",
         instruction=i, modifier=m)
    for i in _ALL_INSTRUCTIONS for m in _ALL_MODIFIERS
] + [
    case("custom_plain", "Custom instructions render bold via the else branch.",
         instruction="U", modifier=""),
    case("custom_needs_escape",
         "A custom instruction containing LaTeX specials must be escaped "
         "(latex.py:46) -- users control this string via the [tag].",
         instruction="R&D", modifier=""),
    case("custom_backslash", "Injection attempt through the [tag].",
         instruction="\\danger", modifier=""),
    case("custom_percent", "'%' would comment out the rest of the row.",
         instruction="50%", modifier=""),
    case("real_uturn", "How an unmapped RWGPS type actually renders.",
         instruction="Uturn", modifier=""),
    case("real_lowercase_right", "Route 56819245's lowercase passthrough.",
         instruction="right", modifier=""),
]

# ---------------------------------------------------------------------------
# latex._entryColor  (latex.py:92-102)
# ---------------------------------------------------------------------------
ENTRY_COLOR = [
    case("none", "Color.NONE -> None (no \\rowcolor emitted).", color="None"),
    case("gray", "Color.GRAY -> '[gray]{0.8}'. Note latex_tests.py:109 still "
         "expects 0.7 -- that test is stale (commit 3fef5b0 'Made gray rows "
         "slightly lighter').", color="Gray"),
    case("yellow", "Color.YELLOW -> '{yellow}'.", color="Yellow"),
]

# ---------------------------------------------------------------------------
# cue.Entry / cue.Route  (cue.py:58-133)
# ---------------------------------------------------------------------------
def entry(instruction="", description="", absolute_distance=0.0, note="",
          modifier="", for_distance=None, color="None"):
    return {"instruction": instruction, "description": description,
            "absolute_distance": absolute_distance, "note": note,
            "modifier": modifier, "for_distance": for_distance, "color": color}


def route(entries, length_mi=10.0, route_id=123, name=None,
          elevation_gain_ft=None):
    return {"entries": entries, "length_mi": length_mi, "id": route_id,
            "name": name, "elevation_gain_ft": elevation_gain_ft}


ENTRY_REPR = [
    case("defaults", "Minimal entry, all optionals defaulted.",
         entry=entry()),
    case("full", "Every field populated.",
         entry=entry("R", "Foo St.", 1.25, "watch the gravel", "Q", 2.5, "Gray")),
    case("for_distance_none", "for_distance None renders as 5 spaces "
         "(cue.py:87-90).", entry=entry("L", "Bar", 1.0, for_distance=None)),
    case("for_distance_zero",
         "for_distance of exactly 0.0 is FALSY, so it renders as 5 spaces just "
         "like None -- a real zero-length leg is indistinguishable from a "
         "missing one (cue.py:87).", entry=entry("L", "Bar", 1.0, for_distance=0.0)),
    case("for_distance_small", "A small but non-zero leg does render.",
         entry=entry("L", "Bar", 1.0, for_distance=0.01)),
    case("distance_from_string",
         "absolute_distance is coerced with float() (cue.py:79), so a string "
         "is accepted -- the CSV path relies on this.",
         entry=entry("L", "Bar", "3.5")),
    case("distance_from_int", "int is coerced to float too.",
         entry=entry("L", "Bar", 4)),
    case("distance_negative", "No validation anywhere; negatives pass through.",
         entry=entry("L", "Bar", -1.5)),
    case("distance_large", "Width formatting with %5.2f on a big number.",
         entry=entry("L", "Bar", 1234.567)),
    case("unicode_description", "Non-ASCII must survive repr under py2.",
         entry=entry("L", "Rue de l'Église", 1.0)),
    case("zwsp_description", "U+200B in a description.",
         entry=entry("L", "A/" + ZWSP + "B", 1.0)),
    case("custom_instruction", "A [tag]-derived instruction.",
         entry=entry("U-Turn", "Bar", 1.0)),
]

ROUTE_REPR = [
    case("empty", "A route with no entries at all.", route=route([])),
    case("minimal", "One entry, no name, no elevation.",
         route=route([entry("L", "Foo", 0.0)])),
    case("full", "Name and elevation present.",
         route=route([entry("", "Start of route", 0.0, for_distance=1.0),
                      entry("R", "Foo St.", 1.0)],
                     length_mi=1.0, route_id=456, name="Test Route",
                     elevation_gain_ft=1000.0)),
    case("string_id", "route_id is stored unvalidated; ridewithgps passes "
         "through whatever it was given, and the old tests assert it is a "
         "STRING while latex._makeHeader:186 needs an int.",
         route=route([entry("L", "Foo", 0.0)], route_id="6260667")),
    case("unicode_name", "Route names reach \\lhead and must survive repr.",
         route=route([entry("L", "Foo", 0.0)], name="Φθινοπωρινός")),
]

# ---------------------------------------------------------------------------
# cue_utils.AdjustStartAndEnd  (cue_utils.py:19-49)
#
# Triggered when an entry's instruction is literally 'start'/'end'
# (case-insensitive), which only happens via a [start]/[end] bracket tag. The
# function deletes from the list it is iterating over, so several of these
# outcomes are emergent rather than designed -- which is precisely why they get
# frozen instead of reasoned about.
# ---------------------------------------------------------------------------
def _base_entries():
    """Mirrors MakeRoute() in cue_utils_tests.py:30-37."""
    return [entry("R", "Start of route", 0.0, for_distance=1.0),
            entry("R", "Entry 1", 1.0, for_distance=0.5),
            entry("R", "Entry 2", 1.5, for_distance=2.5),
            entry("R", "Entry 3", 4.0, for_distance=1.0),
            entry("R", "Entry 4", 5.0, for_distance=3.0),
            entry("R", "End of route", 8.0)]


def _tagged(index, instruction, description="Custom"):
    ents = _base_entries()
    ents[index]["instruction"] = instruction
    ents[index]["description"] = description
    return route(ents, length_mi=8.0, route_id=12345, name="Test Route",
                 elevation_gain_ft=1000.0)


ADJUST_START_END = [
    case("no_tags", "Nothing tagged -- the route must be untouched.",
         route=route(_base_entries(), length_mi=8.0, route_id=12345)),
    case("start_only", "Matches cue_utils_tests.py test_AdjustStartAndEnd_startOnly.",
         route=_tagged(3, "start", "foo")),
    case("end_only", "Matches cue_utils_tests.py test_AdjustStartAndEnd_endOnly.",
         route=_tagged(3, "end", "foo")),
    case("start_uppercase", "The comparison lowercases (cue_utils.py:28), so "
         "'[START]' works.", route=_tagged(3, "START", "foo")),
    case("end_mixed_case", "Route 6260667 ships '[End]'.",
         route=_tagged(3, "End", "foo")),
    case("start_at_index_1", "Tag adjacent to the synthesized first entry.",
         route=_tagged(1, "start", "foo")),
    case("end_at_penultimate", "Tag directly before the last entry.",
         route=_tagged(4, "end", "foo")),
    case("end_at_last_index",
         "The 'end' branch is guarded by `index != len(entries)-1` "
         "(cue_utils.py:37), so a tag on the LAST entry is ignored entirely.",
         route=_tagged(5, "end", "foo")),
    case("start_at_last_index",
         "The 'start' branch has NO such guard and reaches entries[index+1] "
         "(cue_utils.py:34) -- expected to raise IndexError. Recording the "
         "exception is the point.", route=_tagged(5, "start", "foo")),
    case("start_at_index_0",
         "Tagging the first entry makes the function assign the entry to "
         "itself and then delete index 0.", route=_tagged(0, "start", "foo")),
    case("both_start_and_end", "Both tags present, start before end.",
         route=(lambda ents: route(ents, length_mi=8.0, route_id=12345))(
             [dict(e) for e in _base_entries()])),
    case("two_start_tags",
         "Two 'start' tags. The loop mutates the list it is iterating, so the "
         "second tag's index has shifted by the time it is reached.",
         route=None),
    case("two_entry_route",
         "Smallest route where a tag is even meaningful.",
         route=route([entry("start", "Real start", 0.0, for_distance=1.0),
                      entry("R", "Only turn", 1.0)],
                     length_mi=1.0, route_id=1)),
    case("empty_route", "No entries at all -- the loop body never runs.",
         route=route([], length_mi=0.0, route_id=1)),
]

# Fill the two cases that need entry lists built by hand.
for _c in ADJUST_START_END:
    if _c["name"] == "both_start_and_end":
        _e = _base_entries()
        _e[1]["instruction"] = "start"
        _e[1]["description"] = "Real start"
        _e[4]["instruction"] = "end"
        _e[4]["description"] = "Real end"
        _c["route"] = route(_e, length_mi=8.0, route_id=12345)
    elif _c["name"] == "two_start_tags":
        _e = _base_entries()
        _e[1]["instruction"] = "start"
        _e[1]["description"] = "First start"
        _e[3]["instruction"] = "start"
        _e[3]["description"] = "Second start"
        _c["route"] = route(_e, length_mi=8.0, route_id=12345)

WRITERS = [
    ("model/entry_repr.json", ENTRY_REPR),
    ("model/route_repr.json", ROUTE_REPR),
    ("model/adjust_start_end.json", ADJUST_START_END),
    ("strings/escape.json", ESCAPE),
    ("strings/format.json", FORMAT),
    ("strings/clean_description.json", CLEAN_DESCRIPTION),
    ("strings/parse_custom_instruction.json", PARSE_CUSTOM),
    ("strings/instruction_str_to_cue.json", INSTRUCTION_STR),
    ("strings/color_from_instruction.json", COLOR_FROM_INSTRUCTION),
    ("strings/instruction_to_latex.json", INSTRUCTION_TO_LATEX),
    ("strings/entry_color.json", ENTRY_COLOR),
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
        print("%-48s %3d cases" % (relpath, len(cases)))
        total += len(cases)
    print("%-48s %3d cases" % ("TOTAL", total))


if __name__ == "__main__":
    main()

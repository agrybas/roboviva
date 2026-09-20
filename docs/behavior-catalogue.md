# Behavior catalogue

Every quirk worth knowing before you change anything, each tagged and linked to
the test that pins it. All were **verified by running the legacy code**, not by
reading it — several contradict the repo's own test suite.

Tags:

- **Deliberate** — evidence it was intended (comment, commit, or the behaviour
  only makes sense on purpose).
- **Accidental** — a typo or oversight. Preserved because output depends on it.
- **Unknown** — could be either.

This file records *what the legacy system does*. Where the rewrite chooses to
differ, that goes in `harness/KNOWN_DIVERGENCES.md`.

---

## Fatal for the rider

### A `^` in any cue destroys the whole sheet — *accidental*

`_escape` (`latex.py:48-63`) covers `# & $ _ | < > % { }` and U+200B but not
`^`. LaTeX reads a bare caret as a superscript operator outside math mode,
raises `Missing $ inserted`, and `-halt-on-error` means **no PDF is written at
all**. One cue poisons every other cue on the sheet, and the rider sees only
`Guru Meditation: 0xFF`.

Live example: public route **5334050**, whose author typed LaTeX math into the
notes. Has never been renderable.

`test_caret_in_a_description_produces_no_pdf_at_all`,
`test_a_real_public_route_cannot_be_rendered_at_all`

### Non-Latin text cannot be rendered — *unknown*

`inputenc` has no mapping for Greek, Cyrillic, CJK or emoji under the
`fourier`/`helvet` 8-bit font stack. Parsing succeeds; the compile aborts.
Two of eleven real routes in the approval set fail this way.

A limitation of the LaTeX backend rather than of roboviva's own code — and one
of the stronger arguments for the rewrite, since a Unicode-capable renderer
fixes it for nothing.

`test_non_latin_text_cannot_be_rendered`, `test_non_latin_routes_cannot_be_rendered`

**Overall: 3 of 11 real public routes produce no PDF.**
`test_eight_of_eleven_real_routes_render`

---

## Silently wrong output

### Start/End/Generic rows are gray — *accidental*

`cue.py:53` reads `instruction in (Instruction.RIGHT)`. The missing comma makes
that a plain string, so `in` is a **substring** test — and `""` is a substring
of everything. Every `Instruction.NONE` entry gets `Color.GRAY`.

Visually it looks fine, which is why it survived a decade. Fixing it changes
every sheet the service has ever produced.

`test_color_from_instruction[none_empty_string]`

### `~` disappears — *accidental*

Unescaped, and a non-breaking space in LaTeX. Renders, but the character the
rider typed is not in the output. `` ` `` and `"` similarly become typographic
quotes.

`test_tilde_renders_but_is_silently_wrong`

### Emphasis doesn't work in route names — *unknown*

`_makeHeader` escapes the title but never calls `_format`, so `**bold**` in a
route name prints its asterisks. Works everywhere else. `tips.html` advertises
emphasis without mentioning the exception.

`test_emphasis_does_not_work_in_route_names`

### `Sharp left onto Foo` keeps its prefix — *accidental*

`Sharp` is absent from every alternation in `_cleanDescription`
(`ridewithgps.py:254,255,258`) even though `Sharp Left` is a recognized type
(`:268`). Real routes hit this — 47438923 has Sharp Left and Sharp Right points.

`test_clean_description[sharp_left_NOT_stripped]`

### Lowercase `right`/`left` types lose their shading — *accidental*

The instruction mapping is case-sensitive. RideWithGPS emits lowercase types on
some routes (56819245, from "Keep right"), so they pass through as literal text
and never reach `ColorFromInstruction` as `Instruction.RIGHT`. They print as the
words "right" and "left" next to proper R and L rows.

`test_unmapped_types_pass_through_as_literal_text`,
`test_lowercase_instruction_types_reach_the_page`

### A cache entry exactly 60s old shows as "0.0 days" — *accidental*

`views.py:147-155` uses strict comparisons on both sides of each band, so
exactly 60 and exactly 3600 match no branch and fall to the days case.

`test_cache_age_boundaries_fall_through_to_days`

### A flat route looks like an unknown-climb route — *accidental*

`if elevation_gain_ft:` (`latex.py:190`) is falsy for `0`, so both render
`(12.3 mi)` with no feet figure.

`test_zero_climb_is_indistinguishable_from_unknown_climb`

### `for_distance` of exactly 0.0 renders blank — *accidental*

Truthiness test again, in both `Entry.__repr__` (`cue.py:87`) and
`_entryToLatex` (`latex.py:126`). A zero-length leg is indistinguishable from a
missing one.

`test_zero_for_distance_renders_as_empty`

---

## Wasted work

### `pdflatex` runs twice per regeneration — *accidental*

`views.py:87` computes `pdf_data`; `views.py:102` calls `latex2pdf(latex)` again
inside the `open()` block and writes *that*. The first result is discarded.
Since `tex.convert` itself re-runs until `texput.aux` settles, a paginated route
means four `pdflatex` invocations.

`test_regeneration_invokes_pdflatex_twice`

### `quick_threshold_mi` is accepted and ignored — *accidental*

`ridewithgps.py:314` hard-codes `0.1`. The parameter exists in the signature and
does nothing; the repo's own test asserts otherwise and fails.

`test_quick_modifier_from_proximity`

### A turn at mile 0 is never "quick" — *accidental*

`elif entry.prev_absolute_distance:` (`:311`) is a truthiness test and `0.0` is
falsy, so a turn 50 m after the route start is not marked quick.

`test_zero_previous_distance_skips_quick_check`

### `Bear right` works, `bear right` doesn't — *accidental*

The modifier regex (`:309`) has no `re.I`, unlike every rule in
`_cleanDescription`.

`test_slight_modifier_is_case_sensitive`

---

## State corruption

### `/cache/remove` orphans the PDF file — *unknown*

Deletes the shelve row only. The file stays on disk, is still served, and can
never be reclaimed because `/cache/purge` only iterates shelve entries.

`test_cache_remove_orphans_the_pdf_file`

### `/cache/purge` 500s on a missing file — *accidental*

`views.py:206` calls `os.stat` unguarded in the retain branch. The only 5xx the
app produces. It also mutates the shelve while iterating it.

`test_purge_500s_when_a_tracked_pdf_is_missing`

### `[start]` on the last cue crashes — *accidental*

`cue_utils.py:34` reads `entries[index+1]`. The `end` branch is guarded against
this (`:37`); the `start` branch is not. → `IndexError` → error page.

`test_start_tag_on_last_entry_raises_indexerror`

### Two `[start]` tags delete a cue — *accidental*

The function deletes from the list it is iterating. Six entries in, four out,
with the first tagged entry gone entirely — not moved, deleted.

`test_two_start_tags_silently_drop_an_entry`

### `[start]` on the first cue makes a negative distance — *accidental*

With `index == 0`, `entries[index-1]` is the *last* entry, so the "fix up my
predecessor" step rewrites the end of the route using its start.
`for_distance` becomes `-7.0`.

`test_start_tag_on_first_entry_produces_a_negative_distance`

### `[end]` on the last cue leaks the tag — *accidental*

Guarded out, so the entry keeps its raw `end` instruction string and prints
"end" in the Go column.

`test_end_tag_on_last_entry_is_silently_ignored`

---

## Misleading

### An upstream outage is reported as a bad route number — *accidental*

`ridewithgps.py:108-109` collapses every non-304 `HTTPError` into
`RideWithGpsError("Unknown Route ID")`, so a RideWithGPS 500 tells the rider
their route id is invalid.

`test_upstream_outage_is_reported_as_a_bad_route_number`

### Every error page returns HTTP 200 — *deliberate*

See [design-decisions.md](design-decisions.md#all-errors-return-http-200).

`test_every_error_branch_returns_http_200`

### A missing PDF returns 200, not 404 — *deliberate*

`test_missing_pdf_returns_the_regen_page_at_200`

### The `/cache` column labelled "md5" is not an MD5 — *accidental*

It is whatever RideWithGPS sent as the ETag. Today that is a weak validator
whose hex digits are the first 128 bits of the **SHA-256** of the body.

### A fresh clone fails its first request — *accidental*

`pdf_cache/` is gitignored and the app never creates it, so the first route
request returns `Guru Meditation: 0xCE`. Undocumented.

`test_missing_cache_dir_is_the_fresh_clone_experience`

---

## Load-bearing oddities — do not "clean up"

### `api_key=None` in the request URL — *unknown*

Reads like a bug. Is not. RideWithGPS returns the wrapped response shape the
parser needs **only when an `api_key` parameter is present**; remove it and
`ridewithgps.py:122` raises `KeyError: 'route'`.

`test_request_url_carries_literal_api_key_none`,
`test_omitting_api_key_raises_keyerror`

### `>` renders as `⇒`, not `>` — *deliberate*

`latex.py:58` maps `>` to `$\Rightarrow$` while `<` maps to `$<$`. Asymmetric on
purpose: cue sheets write "A > B" for "A leads to B".

`test_escape[greater_than]`

### `_escape` runs before `_format` — *deliberate*

The injection boundary. Escaping first means user text cannot introduce LaTeX;
formatting second means the emphasis markup is trusted output. Preserve the
order.

`test_user_text_cannot_inject_latex`

### `sys.setdefaultencoding("utf8")` affects escaping — *deliberate*

Not incidental: `_escape` mixes byte and unicode strings, and some inputs raise
without it. The harness reproduces the call for exactly this reason.

---

## Dead code

| Thing | Status |
|---|---|
| `Instruction.CROSSES`, `Instruction.CAT_5` | No RideWithGPS string maps to either |
| `getEtagForCSV` | Called by nothing; `UnboundLocalError` on 3 timeouts |
| `getETagAndCuesheet_viaCSV` | Unreachable from the app; endpoint no longer serves CSV (401, or HTML) |
| `tex.escape_latex`, `tex2pdf`, `latex2dvi`, `tex2dvi` | Unused |
| `static_beta/` | Referenced by no Python code |
| `makeLatex` locals at `latex.py:147-148` | Computed, never used |
| `0xBA` error branch | Unreachable via HTTP — the URL converter prevents it |

---

## The repo's own tests are stale

`roboviva/*_tests.py` predate several commits and **fail against current code**.
Do not treat them as a specification.

| Test | Expects | Code does | Since |
|---|---|---|---|
| `latex_tests.py:109` | `[gray]{0.7}` | `[gray]{0.8}` | `3fef5b0` |
| `latex_tests.py:139` | `\textbf{Note:} \emph{…}` | `\newline \textit{…}` | `69ee4d1` |
| `ridewithgps_tests.py:85` | `quick_threshold_mi` honoured | hard-coded `0.1` | — |
| `ridewithgps_tests.py` | `route.id` is a `str` | `latex.py:186` needs an `int` | — |
| `roboviva_tests.py:10` | isolates the shelve file | set after import; has no effect | — |

The 25 formatter cases at `latex_tests.py:191-218` are the exception — all still
accurate, and reused verbatim in the harness corpus.

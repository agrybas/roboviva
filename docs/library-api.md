# Library API

Function reference for the non-Flask modules. Underscore-prefixed helpers are
included because the repo's own tests import them directly and the parity
harness pins them — in practice they are API.

Every function below has a corresponding entry in
`harness/tests/` with observed behaviour recorded as a golden.

---

## `roboviva/cue.py`

```python
ColorFromInstruction(instruction) -> Color
```
Row shading from an instruction. `PIT`/`DANGER` → `YELLOW`; `RIGHT` → `GRAY`;
otherwise `NONE` — except that a missing comma at `cue.py:53` makes the second
test a substring match, so `Instruction.NONE` ("") also returns `GRAY`. See
[data-model.md](data-model.md#the-missing-comma).

```python
class Entry(instruction, description, absolute_distance,
            note="", modifier=Modifier.NONE, for_distance=None, color=Color.NONE)
class Route(entries, length_mi, route_id, route_name=None, elevation_gain_ft=None)
```
Storage only, no behaviour. `Entry.absolute_distance` is coerced with `float()`.
`Route` renames two of its arguments on assignment and takes `length_mi`
*before* `route_id`. Both define `__repr__`.

---

## `roboviva/cue_utils.py`

```python
AdjustStartAndEnd(route) -> None      # mutates route.entries in place
```
Applies `[start]` / `[end]` custom tags: the tagged entry replaces the
synthesized sentinel instead of sitting next to it, and neighbouring
`for_distance` values are patched. Triggered by
`entry.instruction.lower() in ('start', 'end')`, which only happens via a
bracket tag.

Called from the JSON path only (`ridewithgps.py:174`). The CSV path never calls
it.

The implementation deletes from the list it is iterating over, so anything
beyond a single tag is emergent rather than designed. Three behaviours are
frozen as tests because they are bugs someone could otherwise "fix" by
accident:

- `[start]` on the **last** entry raises `IndexError` (`cue_utils.py:34`
  reads `entries[index+1]`; the `end` branch is guarded, this one is not).
- `[end]` on the last entry is **silently ignored**, and the raw `end` string
  leaks into the Go column.
- Two `[start]` tags **delete a cue entirely** — six entries in, four out.
- `[start]` on the **first** entry produces a negative `for_distance`, because
  `entries[index-1]` with `index == 0` is the *last* entry.

---

## `roboviva/ridewithgps.py`

```python
class RideWithGpsError(Exception)
class RWGPS_Entry(instruction_str, description_str, absolute_distance,
                  prev_absolute_distance, next_absolute_distance, note_str)
```

```python
getETagAndCuesheet_viaJSON(route_id, etag=None, api_key=None)
    -> (etag: str, route: cue.Route | None)
```
The one the app uses. Issues
`GET http://ridewithgps.com/routes/<id>.json?api_key=<api_key>&version=2`
with a 5 s timeout, up to 3 attempts on `socket.timeout`. Sends
`If-None-Match` when `etag` is truthy. Returns `(etag, None)` on 304. Raises
`RideWithGpsError` on any other HTTP error, on three timeouts, or on a JSON
decode failure.

> **Do not remove the `api_key` parameter.** It defaults to `None` and is
> interpolated into the URL as the literal string `"None"` (`:89`). That reads
> like a bug and is load-bearing: RideWithGPS returns the wrapped
> `{"route": {..., "metrics": {...}}}` shape the parser expects **only when an
> `api_key` parameter is present**. Without it the response is flat and
> `:122` raises `KeyError: 'route'`. Pinned by
> `test_omitting_api_key_raises_keyerror`.

```python
getETagAndCuesheet_viaCSV(route_id, etag=None)
    -> (etag: str, route: cue.Route | None)
```
Same HTTP contract, parsing `routes/<id>.csv`. Produces a materially poorer
route: **no name, no elevation gain, and no `AdjustStartAndEnd` call**
(`:235-237`).

Unreachable from the app or the CLIs, and **non-functional against the live
service**. `routes/<id>.csv` no longer serves CSV: a plain request gets HTTP
401, while a browser-shaped one gets the route's HTML page. Both fail, but
differently — the 401 becomes a clean `RideWithGpsError`, whereas the HTML gets
far enough into the parser to raise a bare `TypeError` from `float(None)`.

```python
getEtagForCSV(route_id) -> str
```
Test helper, called by nothing. Raises `UnboundLocalError` if all three
attempts time out.

```python
_cleanDescription(description) -> str
```
Ten ordered `re.sub` calls stripping RideWithGPS's redundant turn verbs. Table
in [cue-pipeline.md](cue-pipeline.md#description-normalization). Does not
handle `Sharp`.

```python
_instructionStrToCueInstruction(instruction_str) -> str
```
Case-sensitive lookup; unrecognized strings are **returned verbatim** and
render as bold literal text.

```python
_getModifierFromRWGPSEntry(entry, quick_threshold_mi=0.1) -> Modifier
```
`SLIGHT` if the description starts `Keep|Bear|Slight ` (case-**sensitive**),
else `QUICK` if the gap from the previous entry is under 0.1 mi. Only applies to
`LEFT`/`RIGHT`.

> `quick_threshold_mi` is **accepted and ignored** — `:314` hard-codes `0.1`.
> The repo's own `ridewithgps_tests.py:85` asserts otherwise and has been
> failing for years.

```python
_rawCSVtoRWGPS_Entries(raw_csv_rows) -> [RWGPS_Entry]
_parseCustomInstruction(raw_description) -> str | None
_RWGPS_EntryToCueEntry(rwgps_entry) -> cue.Entry
```
`_parseCustomInstruction` matches `^\s*\[([^\]]+)\]`. `_RWGPS_EntryToCueEntry`
composes the whole per-entry transformation; the order matters and is
diagrammed in [cue-pipeline.md](cue-pipeline.md).

---

## `roboviva/latex.py`

```python
makeLatex(route) -> unicode
```
The entry point: header + one row per entry + footer.

```python
_makeHeader(route) -> unicode
LatexFooter                          # module-level constant
```
`_makeHeader` builds everything from `\documentclass` to the start of the
table. Uses `'%d' % route_id`, so a string id raises `TypeError`. Escapes the
route name but **never calls `_format`**, so `**bold**` in a route title stays
literal — emphasis works in cue rows and not in the header.

```python
_escape(text) -> str
```
The injection boundary. Escapes `\ _ $ # & | < > % { }` and U+200B, in that
order (the backslash rule must run first). Notably `>` becomes `$\Rightarrow$`,
an arrow rather than a literal.

> **Incomplete.** `^ ~ [ ] " `` ` `` are not escaped. A bare `^` is fatal — the
> compile aborts and no PDF is produced.

```python
_format(text) -> str
```
Markdown-ish `*emph*` / `**strong**`, two regex passes. Runs **after**
`_escape`. Its Python 2 replacement template `ur'\emph{\1}'` contains an
invalid escape that raises `re.PatternError` on Python 3.7+; a rewrite must
produce identical output with a valid template. The 25 cases at
`latex_tests.py:191-218` are the best behavioural spec in the repo and are all
still accurate.

```python
_instructionToLatex(instruction, modifier) -> str
_makeClimb(climb_type) -> str
_entryColor(entry) -> str | None
_entryToLatex(entry) -> str
```
`_entryColor` returns `'[gray]{0.8}'` / `'{yellow}'` / `None`.
`_entryToLatex` emits one `supertabular` row; a `for_distance` of `0.0` is
falsy and renders as an empty For column.

---

## `roboviva/tex.py`

Vendored third-party code — `python-tex` 1.8 by Volker Grabsch, **MIT licensed**
rather than the AGPL that covers the rest of the repo. Upstream declared the
project obsolete.

```python
convert(tex_source, input_format, output_format, max_runs=5) -> str
latex2pdf(tex_source, **kwargs) -> str
tex2pdf / latex2dvi / tex2dvi                # unused
escape_latex(s) -> unicode                   # unused by roboviva
```

`convert` asserts `isinstance(tex_source, unicode)`, writes it UTF-8 encoded
into a temp directory, and runs `pdflatex -interaction=batchmode -halt-on-error
-no-shell-escape` repeatedly until `texput.aux` stops changing (that is what
makes `\pageref{LastPage}` resolve). The temp directory is always removed.

All failures are `ValueError`:

| Condition | Message |
|---|---|
| Non-zero exit | the **entire** `texput.log` |
| No output file | `No output file was produced.` |
| Never stabilized | `texput.aux didn't stabilize after 5 runs` |
| Bad format pair | `Unable to handle conversion: x -> y` |

The first is worth noting: the exception carries thousands of lines of font
paths. `views.py` logs it and shows the rider `0xFF`.

---

## `roboviva/enum.py`

```python
Enum(**enums)     # returns type('Enum', (), enums)
```
Three lines, predating any need for the stdlib module. Members are plain `str`.

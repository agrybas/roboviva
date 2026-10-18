# Data model

Everything in `roboviva/cue.py`. Two storage classes and three enum-like
constant groups, with no I/O and no dependencies beyond a three-line enum shim.

## `cue.Entry` — one row of the sheet

```python
Entry(instruction, description, absolute_distance,
      note="", modifier=Modifier.NONE, for_distance=None, color=Color.NONE)
```

| Field | Type | Column | Notes |
|---|---|---|---|
| `instruction` | `str` | **Go** | An `Instruction` value *or* an arbitrary custom string |
| `description` | `str` | **On** | Street name, after normalization |
| `absolute_distance` | `float` | **At** | Miles from the start. **Coerced with `float()`** at `cue.py:79` |
| `note` | `str` | **On** (2nd line) | Rendered italic after `\newline` |
| `modifier` | `str` | **Go** (prefix) | Concatenated in front of the instruction |
| `for_distance` | `float` or `None` | **For** | Miles to the next cue |
| `color` | `str` | row | Background shading |

`absolute_distance` is the only coerced field — the CSV path relies on it,
passing strings straight from `csv.DictReader`.

`__repr__` (`cue.py:85-98`) is the closest thing to a serialization format; the
CLI prints routes and the error paths log them. Its `for_distance` is formatted
`"%5.2f"` only **if truthy**, so `0.0` renders as five spaces — identical to
`None`. A genuine zero-length leg is indistinguishable from a missing one, and
`_entryToLatex` has the same behaviour in the For column.

## `cue.Route` — a sheet

```python
Route(entries, length_mi, route_id, route_name=None, elevation_gain_ft=None)
```

Note the argument order: **`length_mi` comes before `route_id`**, and two
parameters are renamed on assignment (`route_name` → `.name`, `route_id` →
`.id`). Transposing the first two positionals silently produces a route whose
id is its length, which no type check would catch since both are numbers.

| Attribute | From | Notes |
|---|---|---|
| `.entries` | `entries` | list of `Entry` |
| `.length_mi` | `length_mi` | total miles |
| `.id` | `route_id` | **must be an `int`** for rendering — see below |
| `.name` | `route_name` | `None` moves the stats to the right header |
| `.elevation_gain_ft` | `elevation_gain_ft` | `0` behaves like `None` |

**The route id type is contested.** `latex._makeHeader:186` does
`'%d' % route_id`, which raises `TypeError` on a string. But
`ridewithgps.py:169` stores whatever it was handed without coercion, and the
repo's own tests assert `route.id` is a *string*. The web app never trips over
this because Flask's `<int:route_id>` converter guarantees an integer before
the handler runs. A library caller passing a string gets an exception.

`elevation_gain_ft` of `0` is falsy, so `_makeHeader:190` treats a genuinely
flat route the same as one whose climb was never computed — both render
`(12.3 mi)` with no feet figure.

## Instruction

Fifteen values (`cue.py:21-35`). These strings are not internal identifiers —
they are literally what gets printed in the Go column.

| Name | Value | Rendered as |
|---|---|---|
| `LEFT` | `"L"` | **L** |
| `RIGHT` | `"R"` | **R** — and the only value that gets a gray row on purpose |
| `STRAIGHT` | `"S"` | **S** |
| `PIT` | `"PIT"` | **PIT**, yellow row |
| `DANGER` | `"!"` | `\danger` glyph, yellow row |
| `CROSSES` | `"X"` | **X** — *nothing ever produces this* |
| `CAT_HC` | `"CHC"` | mountain glyph labelled HC |
| `CAT_1`…`CAT_4` | `"C1"`…`"C4"` | mountain glyph labelled 1–4 |
| `CAT_5` | `"C5"` | mountain glyph labelled 5 — *nothing ever produces this* |
| `SUMMIT` | `"^"` | mountain glyph labelled **End** |
| `FIRST_AID` | `"+"` | `\Plus` glyph |
| `NONE` | `""` | *(blank Go column)* |

`CROSSES` and `CAT_5` have no RideWithGPS string that maps to them
(`ridewithgps.py:264-296`). They are reachable only through a custom `[X]` or
`[C5]` tag, which takes a different code path and renders as literal text
rather than a glyph.

## Modifier

Three values (`cue.py:38-40`), concatenated in front of the instruction:

| Name | Value | Example |
|---|---|---|
| `NONE` | `""` | `R` |
| `SLIGHT` | `"B"` | `BL` — "bear left" |
| `QUICK` | `"Q"` | `QR` — "quick right" |

Only ever applied to `LEFT` and `RIGHT` (`ridewithgps.py:306`).

## Color

Three values (`cue.py:43-45`), mapped to LaTeX at `latex.py:92-102`:

| Name | Value | `\rowcolor` argument |
|---|---|---|
| `NONE` | `"None"` | *(none emitted)* |
| `GRAY` | `"Gray"` | `[gray]{0.8}` |
| `YELLOW` | `"Yellow"` | `{yellow}` |

The gray was lightened from `0.7` to `0.8` in commit `3fef5b0`; the repo's own
`latex_tests.py:109` still expects `0.7` and has been failing since.

## The missing comma

`ColorFromInstruction` (`cue.py:47-56`) decides row shading:

```python
if instruction in (Instruction.PIT, Instruction.DANGER):
    return Color.YELLOW
elif instruction in (Instruction.RIGHT):     # ← no trailing comma
    return Color.GRAY
```

`(Instruction.RIGHT)` is not a tuple — the parentheses are just grouping, so it
is the plain string `"R"`, and `in` becomes a **substring test**. Since
`Instruction.NONE` is the empty string and `"" in "R"` is `True`, every
`Start` / `End` / `Generic` / `Control` entry comes out **gray**.

Verified against the legacy code, not inferred:
`test_color_from_instruction[none_empty_string]` records `Gray`.

Whether to keep this is a real question. It is almost certainly a typo, but it
produces a visually reasonable result — the start and end rows are shaded like
right turns — and it has shipped that way for a decade. Fixing it changes every
cue sheet the service has ever produced. See
[behavior-catalogue.md](behavior-catalogue.md).

Side effects of the same bug: a custom tag of exactly `"R"` also matches and
goes gray, while `"QR"` does not (not a substring of `"R"`).

## Why a hand-rolled enum

`cue.py` imports `enum` from the repo, not the standard library. `enum.py` is:

```python
def Enum(**enums):
    return type('Enum', (), enums)
```

with the comment *"UGCS Doesn't have newer python versions, so we roll-our-own
enums, here"* (`enum.py:17`) — a deployment constraint, not a preference. See
[design-decisions.md](design-decisions.md#hand-rolled-enums).

The practical consequence: **members are plain `str`**, so `==`, `in`,
substring matching, concatenation and `%`-formatting all work on them. The
missing-comma bug above is only possible because of this, and so is the
modifier concatenation that produces `"QR"`. A rewrite using `enum.Enum` must
keep the *values* identical and will need `.value` in every place the legacy
code uses the member directly.

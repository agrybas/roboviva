# Design decisions

Why Roboviva is built the way it is. Almost none of this was written down, so
most of it is reconstruction. Each entry is tagged:

- **Documented** — stated in a comment, commit message, README or `tips.html`.
- **Inferred** — a reading of the code and its history. Plausible, not certain.

---

## LaTeX and `pdflatex` instead of a PDF library

**Documented.** `README.md:6`:

> *"renders PDFs by converting RWGPS cues into raw LaTeX code which is passed
> to pdflatex via a subprocess. Ugly, but it produces great output."*

The author knew the trade-off and took it. What LaTeX buys, concretely:

- `supertabular` flows a table across pages and columns with no manual
  pagination — the single hardest part of building a cue sheet by hand.
- `\pageref{LastPage}` gives "Page 2 of 3" footers.
- Professional typesetting of a dense two-column layout, free.

What it costs: a ~2 GB TeX installation on the server, a subprocess per render,
seconds of CPU per sheet, and — the part that was probably not anticipated —
**an 8-bit font stack that cannot render non-Latin text at all**. Greek and
Japanese routes are unrenderable, and that is not fixable within this design.

The `python3` branch replaces this with ReportLab specifically to escape the
deployment burden (`README.md:8-11`).

## Hand-rolled enums

**Documented.** `enum.py:17`:

> *"UGCS Doesn't have newer python versions, so we roll-our-own enums, here"*

A deployment constraint, not a preference — the target host had an old Python.
It explains a lot of the codebase's style, and it is exactly the kind of
constraint that has since expired: the stdlib `enum` module has been available
since Python 3.4.

The consequence outlives the cause. Because members are plain strings, `==`,
`in`, substring matching and concatenation all work on them — which is what
makes both the `"QR"` modifier concatenation and the missing-comma bug possible.

## Vendoring `python-tex`

**Documented.** `tex.py:3`: *"The python-tex project is obsolete!"*, with the
original MIT licence retained in the header. Upstream was dead, the code was
small and did exactly one job well, so it was copied in.

Worth knowing: **`tex.py` is MIT while the rest of the repo is AGPLv3.** Do not
assume a uniform licence when moving code around.

## ETag-based caching in a shelve DB

**Inferred.** Two observations drive it:

1. The expensive resource is `pdflatex`, not the download. A conditional GET
   that comes back 304 skips seconds of CPU, not milliseconds of network.
2. RideWithGPS already maintains a perfectly good version identifier. Using
   their ETag means Roboviva never has to decide when a cached sheet is stale —
   the answer arrives with the response.

`shelve` (a dbm-backed dict) rather than SQLite or Redis is consistent with the
rest of the design: no daemon, no schema, no dependency. It stores
`route_id → (etag, timestamp)` and nothing else.

The weakness is that the two caches — the shelve DB and `pdf_cache/` — are
independent, and nothing keeps them consistent. See
[request-lifecycle.md](request-lifecycle.md#two-caches-one-key).

## Redirecting instead of returning the PDF

**Inferred.** `handle_request` always ends in a 302 to `/pdfs/<id>.pdf` rather
than returning bytes. This gives a stable, shareable, browser-cacheable URL for
each sheet, and lets the front end be four lines of JavaScript
(`window.open("routes/" + value)`). A rider can bookmark the PDF URL and get
the cached copy without re-triggering the pipeline.

## Custom instructions as `[tags]` inside the description

**Inferred.** Roboviva has no editing UI and no database — RideWithGPS owns all
the data. So any extension mechanism had to ride inside a field RideWithGPS
already offers. A bracketed prefix in the free-text description is about the
least intrusive option available, and it degrades gracefully: a rider who views
the route in RideWithGPS just sees `[U]` at the front of the text.

The same reasoning explains `[start]`/`[end]` and the `*emphasis*` syntax. All
three are conventions layered onto someone else's text field.

## Markdown-ish emphasis instead of raw LaTeX passthrough

**Inferred**, and it is a security decision. `_escape` runs first and
neutralizes every LaTeX special; `_format` then converts `*`/`**` into `\emph`
and `\textbf`. Riders get formatting without being able to inject commands into
a compiler running on the server.

**Preserve this ordering.** It is the only thing standing between an editable
public text field and `pdflatex`. Public route 5334050 is a live demonstration:
its author typed real LaTeX math into the notes, and the escaping neutralized
all of it — the render fails on an unescaped `^`, but nothing executes.

The escape set being incomplete is a bug, not a design decision. `^ ~ [ ] " ``
` `` all pass through.

## All errors return HTTP 200

**Inferred.** Every failure path renders `error.html` with status 200, and a
missing PDF returns `regen.html` at 200 rather than 404. The apparent motive is
presentational: a styled page with the site's colour bars, rather than whatever
a browser or an intermediary proxy would substitute for a 4xx/5xx.

The costs are real and worth revisiting in a rewrite:

- Monitoring cannot distinguish a healthy service from a broken one.
- Caches and crawlers treat every error as a successful response.
- `curl -f` and similar tooling see success.

The one exception is unintentional: `/cache/purge` can raise `OSError` and
produce a genuine 500.

## `sys.setdefaultencoding("utf8")`

**Documented** as intent at `__init__.py:24` — *"Get ourselves into utf8 mode,
so we don't have ascii / unicode headaches"* — though the technique itself was
already discouraged when it was written. It requires `reload(sys)` to reach a
function Python deliberately removes at startup, and it changes implicit
`str`/`unicode` coercion **process-wide**.

It is not incidental: `_escape` mixes byte strings and unicode, and without the
override some inputs raise `UnicodeDecodeError`. The parity harness reproduces
the call for exactly that reason (`harness/oracle/bridge.py`).

There is no Python 3 equivalent, and none is needed — the distinction it was
papering over does not exist there. This is one of the clearest signals that
the codebase is straining against its interpreter.

## The `api_key=None` in every request URL

**Inferred, and important.** `ridewithgps.py:89` interpolates the *default*
argument into the URL, so every production request advertises the literal
string `"None"` as its API key. It reads unmistakably like a bug.

It is load-bearing. RideWithGPS returns the wrapped
`{"route": {..., "metrics": {...}}}` shape the parser expects **only when an
`api_key` parameter is present**. Omit it and the response is flat, and
`ridewithgps.py:122` raises `KeyError: 'route'`.

Whether the original author knew this is unknowable. Either way, a rewrite that
tidies the parameter away silently switches response formats. Pinned by
`test_omitting_api_key_raises_keyerror`.

## Two fetch paths, one used

**Inferred.** `getETagAndCuesheet_viaCSV` predates the JSON version — the
README's tagline is still *"Convert RideWithGPS Cue .csv's into a nice PDF"* —
and the JSON export superseded it because it carries the route name and
elevation gain, which the CSV does not.

The CSV path was left in place and is now dead twice over: nothing calls it,
and `routes/<id>.csv` no longer returns CSV at all.

## The 0.1 mi "quick turn" threshold

**Inferred**, and evidently unfinished. `_getModifierFromRWGPSEntry` takes a
`quick_threshold_mi=0.1` parameter and then ignores it, comparing against a
hard-coded `0.1` at `:314`. The repo's own test passes a different threshold
and asserts it is honoured — a test that has been failing for years.

So the intent to make it configurable existed and was never completed. A
rewrite should either wire the parameter up or delete it.

## `static_beta/`

An abandoned UI variant — same page with a "BETA" badge and no footer. **No
Python code references it** on this branch. The direction continued on
`python3`. Safe to delete.

---

## Constraints that have expired

Worth stating plainly, since several shaped decisions that no longer make sense:

| Constraint | Then | Now |
|---|---|---|
| Old Python on the deploy host | hand-rolled enums, no stdlib `enum` | `enum` has shipped since 3.4 |
| Python 2 `str`/`unicode` split | `setdefaultencoding` hack | does not exist in Python 3 |
| `python-tex` upstream dead | vendored a copy | still dead; the whole backend is replaceable |
| RideWithGPS CSV export | the original data path | 401 or HTML now; JSON is the only option |
| No PDF library good enough | LaTeX subprocess | ReportLab exists, and handles Unicode |

The one constraint that has **not** expired is RideWithGPS ownership of the
data. Roboviva still has no UI, no accounts and no storage of its own, and the
`[tag]` conventions still have to live inside someone else's text field.

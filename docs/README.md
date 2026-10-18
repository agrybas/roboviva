# Roboviva — contributor documentation

Roboviva turns a RideWithGPS route number into a printable cue sheet PDF: the
turn-by-turn directions a cyclist clips to their handlebar bag. You give it
`ridewithgps.com/routes/54079314`, it gives you a two-column, letter-paper
sheet with columns for **Go / At / On / For**.

```
GET /roboviva/routes/54079314
      │
      ├─ ask RideWithGPS for the route (conditionally, using a cached ETag)
      ├─ translate its course points into cue entries
      ├─ render those to LaTeX, run pdflatex
      ├─ cache the PDF on disk
      └─ 302 → /roboviva/pdfs/54079314.pdf
```

It was written in 2014–2015 by Mike Kocurek for NYCC club rides, and the design
still reflects that: a small Flask app, no database, no accounts, no build step,
and a LaTeX toolchain doing the typesetting because that is what produced the
best-looking output.

## Which tree am I in?

| Path | What it is | Status |
|---|---|---|
| `roboviva/`, `*.py` at the root | The legacy service. **Python 2 only** — it does not parse under Python 3. | Frozen. Do not "fix" things here; changes invalidate the goldens. |
| `harness/` | The parity harness: an input corpus, golden outputs recorded from the legacy code, and a Python 3 pytest suite. | Active. This is how the rewrite is proven equivalent. |
| `docs/` | These documents. | Active. |

The legacy code cannot run on a modern machine, so the harness runs it inside a
pinned container (`harness/oracle/`). You do not need Python 2 or a TeX
installation locally — you need Docker.

```bash
harness/oracle/fetch_debs.sh        # one-time: pre-fetch a large TeX package
harness/oracle/run.sh build         # build the Python 2 + TeX Live image
harness/oracle/run.sh generate      # record goldens from the legacy code

python3 -m venv harness/.venv
harness/.venv/bin/pip install -r harness/requirements-dev.txt
cd harness && ../harness/.venv/bin/python -m pytest --sut=legacy
```

That last command must be green. It runs the Python 3 test suite against the
Python 2 original, which is what makes the harness trustworthy: if it passes,
the tests describe the real system rather than someone's idea of it.

## Reading order

1. **[architecture.md](architecture.md)** — the pieces and how they connect.
2. **[request-lifecycle.md](request-lifecycle.md)** — what one request does, and
   how the two-level cache works.
3. **[cue-pipeline.md](cue-pipeline.md)** — the data transformation, stage by
   stage. The most important document here.
4. **[data-model.md](data-model.md)** — `Entry`, `Route`, and the three enums.
5. **[http-api.md](http-api.md)** — endpoint reference.
6. **[library-api.md](library-api.md)** — function reference.
7. **[authoring-cuesheets.md](authoring-cuesheets.md)** — the user-facing
   feature set, including one shipped feature that is documented nowhere else.
8. **[design-decisions.md](design-decisions.md)** — why it is built this way.
9. **[behavior-catalogue.md](behavior-catalogue.md)** — the quirks, each linked
   to the test that pins it. Read before changing anything.

## Conventions in these documents

Almost none of the original rationale was written down, so it has been
reconstructed. Every claim about *why* is tagged:

- **Documented** — stated in a comment, a commit message, the README, or
  `tips.html`. The source is cited.
- **Inferred** — a reading of the code and its history. Plausible, not certain.

Claims about *what the code does* are cited as `file.py:line` and are backed by
a test in `harness/tests/`. They were verified by running the legacy code, not
by reading it — several turned out to contradict the repo's own test suite,
which has been stale for years.

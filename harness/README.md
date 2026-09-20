# Roboviva parity harness

An executable definition of what the legacy Python 2 service does, so a rewrite
can be **proven** equivalent rather than assumed to be.

The legacy code does not run on a modern machine — `roboviva/latex.py` is not
even valid Python 3 syntax — so the harness runs it inside a pinned container
and records what it produces. The Python 3 test suite then asserts the rewrite
reproduces those recordings.

```
corpus/     inputs, plain JSON, no Python
              ↓  run through the legacy code in the oracle container
golden/     committed expected outputs
              ↓  asserted by
tests/      Python 3 pytest suite  →  the rewrite (or the legacy code itself)
```

## Setup

Requires **Docker**. You do not need Python 2 or a TeX installation.

```bash
harness/oracle/fetch_debs.sh      # one-time, ~513MB, resumable
harness/oracle/run.sh build       # build the image (~2.5GB, slow first time)

python3 -m venv harness/.venv
harness/.venv/bin/pip install -r harness/requirements-dev.txt
```

On SELinux hosts (Fedora, RHEL) containers run with `--security-opt
label=disable` rather than a `:z` mount flag, so your working tree is never
relabelled.

## Running

```bash
cd harness

# The decisive check: the py3 suite against the py2 original.
# This MUST pass. If it fails, the harness is wrong, not the code.
../harness/.venv/bin/python -m pytest --sut=legacy

# Against the rewrite. Fails until the rewrite exists -- that is the point.
../harness/.venv/bin/python -m pytest

# Has RideWithGPS changed shape under the fixtures? (network, opt-in)
../harness/.venv/bin/python -m pytest -m live
```

**509 tests, ~30 seconds** against the legacy oracle.

## Regenerating goldens

```bash
harness/oracle/run.sh generate    # rewrite golden/ from the legacy code
harness/oracle/run.sh verify      # regenerate to a temp dir and diff
harness/oracle/run.sh shell       # poke at the legacy code interactively
```

`verify` must report *"goldens are reproducible"*. If it does not, either the
legacy code changed or the toolchain did — `golden/environment.json` records
the Python and pdfTeX versions the goldens were made with.

**A golden diff in a pull request is a behaviour change.** Review it as one.

## Layout

| Path | What |
|---|---|
| `corpus/*.json` | Input cases. Every case carries a `why` explaining what it pins. |
| `corpus/approval/` | Eleven real RideWithGPS routes, recorded verbatim. |
| `golden/` | Expected outputs, generated and committed. |
| `golden/latex/documents/*.tex` | Whole LaTeX documents — the byte-exact contract. |
| `oracle/` | Everything Python 2. Runs only inside the container. |
| `tests/sut.py` | **The parity contract.** One adapter, two backends. |
| `tests/conftest.py` | Corpus/golden loading and the `--sut` option. |

## Adding a case

1. Add it to the relevant `corpus/build_*_corpus.py`, with a `why` that says
   what behaviour it pins. A case that cannot explain itself does not belong.
2. `python3 harness/corpus/build_*_corpus.py`
3. `harness/oracle/run.sh generate`
4. **Read the new golden.** It is the legacy behaviour, whatever that turns out
   to be — several cases here recorded the opposite of what the code appeared
   to do.
5. Add an assertion in `tests/` if the behaviour deserves a named test rather
   than just parity coverage.

Never write an expected value by hand. The whole point is that goldens are
observed, not asserted from a reading of the source.

## How the rewrite plugs in

`tests/sut.py` defines every operation the harness exercises, as JSON in and
JSON out. The rewrite is free to use dataclasses, real enums, pydantic,
whatever — it only has to satisfy `NewBackend.call()`.

Cue entries cross the boundary as
`{instruction, description, absolute_distance, note, modifier, for_distance, color}`
and routes as `{name, id, entries, elevation_gain_ft, length_mi}`.

Until then `NewBackend` raises `NotImplementedError` naming the missing
operation — deliberately a failure and not a skip, so the work remaining is
always visible.

## Intentional divergences

When the rewrite should behave *differently* — and it should, in several places
— record it in [KNOWN_DIVERGENCES.md](KNOWN_DIVERGENCES.md) and mark the test
`xfail(strict=True)`. Strict means a divergence that later disappears fails the
build instead of passing quietly.

## Notes

- **Nothing in the test suite touches the network.** Fixtures are recorded
  deliberately by `oracle/record_fixtures.py`, and the container runs with
  `--network none`.
- **PDFs are compared by summary**, not bytes — `/ID` and `/CreationDate` change
  every run. The summary is page count, page geometry and the normalized text
  layer, extracted with the same `pypdf` version on both sides. The `.tex`
  source is the byte-exact contract.
- **The clock is frozen** during HTTP scenarios, because `/cache` renders ages
  as text.
- `corpus/approval/` fixtures have `route.track_points` stripped (93% of the
  payload, never read by the parser). The original size and SHA-256 are
  recorded in each file's `provenance` block.

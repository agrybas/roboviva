# HTTP API

Six routes, all registered on the `roboviva` blueprint under the `/roboviva`
prefix (`roboviva/__init__.py:30-31`), plus static assets.

**The whole service is GET-only, unauthenticated, and has no CSRF protection,
no rate limiting, and no JSON API.** No route declares `methods=`, so Flask
allows `GET`, `HEAD` and `OPTIONS` and returns 405 for anything else. That
includes the three cache-administration endpoints, which anyone who can reach
the service can call. The exposure is limited — the cache is a rebuildable
derivative of public data — but it is a real consideration for how a rewrite
gets deployed.

| Method | Path | Handler | Success |
|---|---|---|---|
| GET | `/roboviva/` | `index` | 200 `text/html` |
| GET | `/roboviva/routes/<int:route_id>` | `handle_request` | **302** |
| GET | `/roboviva/pdfs/<int:route_id>.pdf` | `get_pdf` | 200 `application/pdf` |
| GET | `/roboviva/cache` | `dump_cache` | 200 `text/html` |
| GET | `/roboviva/cache/remove/<int:route_id>` | `remove_route` | 200 `text/html` |
| GET | `/roboviva/cache/purge/<int:delete_older_than>` | `purge_cache` | 200 `text/html` |

---

## `GET /roboviva/`

Serves `roboviva/static/index.html` (`views.py:31-33`). A single text input
restricted to digits; pressing Enter opens `routes/<value>` in a new tab
(`static/robo.js:1-5`).

---

## `GET /roboviva/routes/<int:route_id>`

The main entry point. Fetches, renders, caches, and redirects. Full behaviour in
[request-lifecycle.md](request-lifecycle.md).

**Success** — always `302`, never the PDF itself:

```
HTTP/1.1 302 FOUND
Location: /roboviva/pdfs/<route_id>.pdf
```

**Failures** — all return **HTTP 200** with a styled `error.html`:

| Cause | `views.py` | Message |
|---|---|---|
| Route not found upstream, or 3 timeouts | :54-56 | `'<id>' is not a valid RideWithGPS Route :(` |
| Any other fetch/parse error | :57-61 | `Error querying RideWithGPS` · `{Guru Meditation: 0xFA}` |
| LaTeX generation raised | :76-83 | `Internal Error :(` · `{Guru Meditation: 0xBA - Cue Parsing Failed}` |
| `pdflatex` failed | :86-94 | `Internal Error :(` · `{Guru Meditation: 0xFF - Error Rendering PDF}` |
| Could not write the PDF | :100-108 | `Internal Error :(` · `{Guru Meditation: 0xCE - Error writing PDF}` |

Two things to know about that table:

- An upstream **500 produces the "not a valid route" message**, because
  `ridewithgps.py:108-109` maps every non-304 `HTTPError` to
  `RideWithGpsError`. The rider is blamed for an outage.
- The `0xBA` branch looks unreachable through HTTP: `makeLatex` only raises on
  a non-integer route id, and the URL converter guarantees an integer.

`0xFF` is the one riders actually hit — any cue containing a `^`, or any
non-Latin text, aborts the render. See
[behavior-catalogue.md](behavior-catalogue.md).

**404s** come from the URL converter, not the handler: `/routes/abc` and
`/routes/-1` never reach `handle_request`.

---

## `GET /roboviva/pdfs/<int:route_id>.pdf`

Serves the cached file (`views.py:118-129`).

```
HTTP/1.1 200 OK
Content-Type: application/pdf
```

`as_attachment=False`, so the PDF displays inline. On Flask 1.x that means
**no `Content-Disposition` header at all**; modern Flask emits
`inline; filename=<id>.pdf`. That difference is asserted explicitly in
`test_pdf_is_served_inline_as_application_pdf` so a rewrite decides about it
rather than drifting.

If the file is missing, the response is `regen.html` at **HTTP 200** — not a
404 — offering a link back to `/routes/<id>` to rebuild it.

---

## `GET /roboviva/cache`

Hand-built HTML (`views.py:131-161`), not a template. Body shape:

```
Cache has <N> entries
<table border=1>
  <tr><th>route id</th><th>md5</th><th>age</th><th>Remove?</th></tr>
  <tr>
    <td><route_id></td>
    <td><etag></td>
    <td><age></td>
    <td><a href=/roboviva/cache/remove/<id>>Remove</a></td>
  </tr>
</table>
```

Rows are sorted by `(timestamp, route_id, etag)` — oldest first.

The column labelled **md5** is not an MD5. It is whatever RideWithGPS sent as
the `ETag`, which today is a weak validator whose hex digits are the first 128
bits of the **SHA-256** of the response body. The name is a leftover.

Age formatting (`views.py:147-155`) has a hole at the exact boundaries: an age
of precisely 60 or 3600 seconds matches no branch and renders as `0.0 days`.

---

## `GET /roboviva/cache/remove/<int:route_id>`

Deletes the shelve entry and returns a bare string (`views.py:163-173`):

```
<route_id> removed from cache
<route_id> not found in cache
```

**It does not delete the PDF file.** The file stays on disk, is still served by
`/pdfs/<id>.pdf`, and can never be reclaimed by `/cache/purge` because purge
only iterates shelve entries.

---

## `GET /roboviva/cache/purge/<int:delete_older_than>`

`delete_older_than` is in **seconds** (`views.py:175-212`). Entries older than
that lose both their shelve row and their file; newer ones are counted.

```
Cache has <N> entries
<table border=1>
  <tr><th>route id</th><th>md5</th><th>age (s)</th><th>status</th></tr>
  ...status is DELETED, ERROR, or empty...
</table>
<X> kB deleted, <Y> kB remaining
```

The kB figures use integer division, so anything under 1 kB reports as 0.

**This endpoint can return 500.** The retain branch calls `os.stat` unguarded
(`views.py:206`), so a shelve entry whose file was removed out of band raises
`OSError`. It is the only 5xx the application produces. It also mutates the
shelve while iterating it, so which entries get processed before the failure is
not well defined.

---

## Static assets

Served from `roboviva/static/` at **two** URL prefixes — `/roboviva/robo.css`
(blueprint) and `/robo.css` (app). See
[architecture.md](architecture.md#static-files-are-mounted-twice); the prefixed
form is the one the HTML's relative links depend on.

Files: `index.html`, `tips.html`, `robo.css`, `robo.js`, and five `tips_*.gif`
screenshots. `static_beta/` is served by nothing.

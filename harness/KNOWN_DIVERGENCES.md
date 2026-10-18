# Known divergences

Places where the rewrite deliberately behaves differently from the legacy
service. **Currently empty of accepted divergences** — the rewrite has not
started. This file is the template and the queue.

`docs/behavior-catalogue.md` records what the legacy system *does*. This file
records where we chose to differ, and why.

## Process

1. Decide the divergence is intentional. If you are not sure, it is a bug in
   the rewrite, not a divergence.
2. Add an entry below: what changes, why, and who is affected.
3. Mark the parity test `@pytest.mark.xfail(strict=True, reason="see
   KNOWN_DIVERGENCES.md#<anchor>")`.

`strict=True` matters: if the divergence later disappears, the build fails
instead of passing silently. A divergence that stops happening is news.

---

## Candidates awaiting a decision

Each of these is pinned by a passing test today. Changing any of them is
defensible; changing one *by accident* is not.

### Almost certainly fix

| Behaviour | Test | Note |
|---|---|---|
| `pdflatex` runs twice per regeneration | `test_regeneration_invokes_pdflatex_twice` | Pure waste. No output change. |
| `^` in a description aborts the whole render | `test_caret_in_a_description_produces_no_pdf_at_all` | Breaks a real public route. Fix by completing the escape set. |
| `/cache/purge` 500s on a missing PDF | `test_purge_500s_when_a_tracked_pdf_is_missing` | Unguarded `os.stat`. |
| `[start]` on the last cue raises `IndexError` | `test_start_tag_on_last_entry_raises_indexerror` | Guard it like the `end` branch already is. |
| Two `[start]` tags delete a cue | `test_two_start_tags_silently_drop_an_entry` | Silent data loss. |
| Cache age of exactly 60s shows "0.0 days" | `test_cache_age_boundaries_fall_through_to_days` | Off-by-one in the comparison chain. |
| Upstream 500 reported as a bad route id | `test_upstream_outage_is_reported_as_a_bad_route_number` | Misleads the rider. |
| `quick_threshold_mi` accepted and ignored | `test_quick_modifier_from_proximity` | Wire it up or delete it. |
| Non-Latin routes cannot render | `test_non_latin_routes_cannot_be_rendered` | Free on any Unicode-capable backend. |

### Needs a judgement call

| Behaviour | Test | The tension |
|---|---|---|
| Start/End/Generic rows are gray | `test_color_from_instruction[none_empty_string]` | Caused by a missing comma, but the output looks deliberate and has shipped for a decade. Fixing it changes every sheet ever produced. |
| All error pages return HTTP 200 | `test_every_error_branch_returns_http_200` | Deliberate presentation choice; costs monitoring and cache correctness. |
| Missing PDF returns 200, not 404 | `test_missing_pdf_returns_the_regen_page_at_200` | Same trade-off, plus the regen page is genuinely useful. |
| `/cache/remove` orphans the PDF file | `test_cache_remove_orphans_the_pdf_file` | Slow disk leak, or intentional "keep serving what we have"? |
| Cache admin endpoints are unauthenticated | `test_service_is_read_only_and_unauthenticated` | Low stakes today; a deployment decision for the rewrite. |
| `>` renders as `⇒` | `test_escape[greater_than]` | Almost certainly a cue-sheet convention worth keeping. |
| `Bear right` works, `bear right` does not | `test_slight_modifier_is_case_sensitive` | Fixing it changes existing sheets that happen to use lowercase. |
| A turn at mile 0 is never "quick" | `test_zero_previous_distance_skips_quick_check` | Same. |
| Emphasis does not work in route names | `test_emphasis_does_not_work_in_route_names` | Inconsistent with `tips.html`, but adding it changes existing titles. |
| `Sharp left onto Foo` keeps its prefix | `test_clean_description[sharp_left_NOT_stripped]` | Clear oversight; fixing it shortens real cue text. |
| Lowercase `right`/`left` types pass through | `test_unmapped_types_pass_through_as_literal_text` | Fixing means case-insensitive matching, which may catch other things. |

### Do not change without understanding why

| Behaviour | Test | Why it is load-bearing |
|---|---|---|
| `api_key=None` in the request URL | `test_request_url_carries_literal_api_key_none` | Removing it silently switches RideWithGPS to a response shape the parser cannot read. |
| `_escape` runs before `_format` | `test_user_text_cannot_inject_latex` | The injection boundary. Reversing it lets riders inject LaTeX. |
| Two-level cache keyed on the upstream ETag | `test_unchanged_etag_skips_rendering_entirely` | Avoids seconds of CPU per request. |
| Handler redirects rather than returning bytes | `test_route_request_redirects_to_the_pdf` | Gives each sheet a stable shareable URL. |

### Probably delete

| Thing | Note |
|---|---|
| `getETagAndCuesheet_viaCSV` | Unreachable from the app and non-functional upstream. Still public API with tests. |
| `getEtagForCSV` | Called by nothing; `UnboundLocalError` on three timeouts. |
| `Instruction.CROSSES`, `Instruction.CAT_5` | No RideWithGPS input produces either. |
| `static_beta/` | Referenced by no code. |
| `tex.escape_latex`, `tex2pdf`, `latex2dvi`, `tex2dvi` | Unused. |

---

## Accepted divergences

*(none yet)*

<!--
Template:

### <short title>

**Legacy:** what it did.
**Rewrite:** what it does now.
**Why:** the reasoning.
**Affects:** who notices, and how.
**Tests:** the xfail'd test names.
-->

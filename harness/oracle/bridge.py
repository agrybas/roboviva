# -*- coding: utf-8 -*-
"""Python 2 stdio bridge exposing the legacy Roboviva code to the py3 harness.

Speaks line-delimited JSON on stdin/stdout:

    -> {"id": 1, "op": "escape", "args": {"text": "a & b"}}
    <- {"id": 1, "ok": true, "result": "a \\& b"}
    <- {"id": 2, "ok": false, "error": {"type": "KeyError", "message": "'route'"}}

Two consumers:

  * generate.py, which drives it to write harness/golden/
  * pytest --sut=legacy, which drives it to prove the harness is green against
    the original code before any rewrite exists

Nothing here modifies the legacy modules. If a behavior looks wrong, it gets
recorded as-is -- that is the entire point.
"""
import json
import os
import sys
import traceback

# The legacy package uses implicit relative imports ("import cue" from inside
# roboviva/), so the package directory itself has to be importable -- the same
# assumption roboviva/*_tests.py make. Repo root comes too, for `import config`
# and the CLI scripts.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.normpath(os.path.join(_HERE, "..", ".."))
_PKG = os.path.join(_REPO, "roboviva")
for _p in (_PKG, _REPO):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# roboviva/__init__.py:25-26 does this at import time, so it is in effect for
# every real entry point (web app and both CLI scripts). _escape() mixes str
# and unicode operands, whose behavior depends on the default encoding, so the
# bridge has to reproduce it or it would be measuring a different program.
reload(sys)
sys.setdefaultencoding("utf8")

import cue          # noqa: E402
import cue_utils    # noqa: E402
import latex        # noqa: E402
import ridewithgps  # noqa: E402
import tex          # noqa: E402

from stub_net import ScriptedNet  # noqa: E402


# --------------------------------------------------------------------------
# (de)serialization
# --------------------------------------------------------------------------

def entry_to_dict(e):
    return {
        "instruction": e.instruction,
        "description": e.description,
        "absolute_distance": e.absolute_distance,
        "note": e.note,
        "modifier": e.modifier,
        "for_distance": e.for_distance,
        "color": e.color,
    }


def dict_to_entry(d):
    return cue.Entry(
        d["instruction"],
        d["description"],
        d["absolute_distance"],
        d.get("note", ""),
        d.get("modifier", cue.Modifier.NONE),
        d.get("for_distance"),
        d.get("color", cue.Color.NONE),
    )


def route_to_dict(r):
    return {
        "name": r.name,
        "id": r.id,
        "entries": [entry_to_dict(e) for e in r.entries],
        "elevation_gain_ft": r.elevation_gain_ft,
        "length_mi": r.length_mi,
    }


def dict_to_route(d):
    return cue.Route(
        [dict_to_entry(e) for e in d["entries"]],
        d["length_mi"],
        d["id"],
        d.get("name"),
        d.get("elevation_gain_ft"),
    )


def dict_to_rwgps_entry(d):
    return ridewithgps.RWGPS_Entry(
        instruction_str=d["instruction_str"],
        description_str=d["description_str"],
        absolute_distance=d["absolute_distance"],
        prev_absolute_distance=d.get("prev_absolute_distance"),
        next_absolute_distance=d.get("next_absolute_distance"),
        note_str=d.get("note_str"),
    )


def rwgps_entry_to_dict(e):
    return {
        "instruction_str": e.instruction_str,
        "description_str": e.description_str,
        "absolute_distance": e.absolute_distance,
        "prev_absolute_distance": e.prev_absolute_distance,
        "next_absolute_distance": e.next_absolute_distance,
        "note_str": e.note_str,
    }


# --------------------------------------------------------------------------
# operations
# --------------------------------------------------------------------------

def op_ping(args):
    return {
        "python": sys.version,
        "default_encoding": sys.getdefaultencoding(),
        "repo": _REPO,
    }


def op_enums(args):
    """Dump the enum vocabulary so the harness can assert the exact values."""
    def members(klass):
        return dict((k, v) for k, v in klass.__dict__.items()
                    if not k.startswith("__"))
    return {
        "Instruction": members(cue.Instruction),
        "Modifier": members(cue.Modifier),
        "Color": members(cue.Color),
    }


def op_escape(args):
    return latex._escape(args["text"])


def op_format_markup(args):
    return latex._format(args["text"])


def op_instruction_to_latex(args):
    return latex._instructionToLatex(args["instruction"], args["modifier"])


def op_make_climb(args):
    return latex._makeClimb(args["climb_type"])


def op_entry_color(args):
    ent = cue.Entry(cue.Instruction.NONE, "", 0.0, color=args["color"])
    return latex._entryColor(ent)


def op_color_from_instruction(args):
    return cue.ColorFromInstruction(args["instruction"])


def op_clean_description(args):
    return ridewithgps._cleanDescription(args["description"])


def op_parse_custom_instruction(args):
    return ridewithgps._parseCustomInstruction(args["description"])


def op_instruction_str_to_cue(args):
    return ridewithgps._instructionStrToCueInstruction(args["instruction_str"])


def op_modifier_for(args):
    ent = dict_to_rwgps_entry(args["entry"])
    if "quick_threshold_mi" in args and args["quick_threshold_mi"] is not None:
        return ridewithgps._getModifierFromRWGPSEntry(
            ent, args["quick_threshold_mi"])
    return ridewithgps._getModifierFromRWGPSEntry(ent)


def op_entry_from_rwgps(args):
    return entry_to_dict(
        ridewithgps._RWGPS_EntryToCueEntry(dict_to_rwgps_entry(args["entry"])))


def op_csv_rows_to_entries(args):
    rows = args["rows"]
    if args.get("encode_utf8"):
        # csv.DictReader hands the real code byte strings, not unicode.
        rows = [dict((k.encode("utf-8"), (v.encode("utf-8")
                                          if isinstance(v, unicode) else v))
                     for k, v in row.items()) for row in rows]
    return [rwgps_entry_to_dict(e)
            for e in ridewithgps._rawCSVtoRWGPS_Entries(rows)]


def op_adjust_start_and_end(args):
    route = dict_to_route(args["route"])
    cue_utils.AdjustStartAndEnd(route)
    return route_to_dict(route)


def op_entry_repr(args):
    return repr(dict_to_entry(args["entry"]))


def op_route_repr(args):
    return repr(dict_to_route(args["route"]))


def op_entry_to_latex_row(args):
    return latex._entryToLatex(dict_to_entry(args["entry"]))


def op_make_latex(args):
    return latex.makeLatex(dict_to_route(args["route"]))


def op_make_header(args):
    return latex._makeHeader(dict_to_route(args["route"]))


def op_latex_footer(args):
    return latex.LatexFooter


def _reset_app_modules():
    """Drop the Flask app and its deps so the next import rebuilds them.

    roboviva/__init__.py wires the app at IMPORT time -- it reads config and
    calls shelve.init_app(app) on line 38 -- so config has to be patched before
    the import, and every scenario needs a fresh import to get its own cache
    directory and shelve file. (roboviva_tests.py sets SHELVE_FILENAME *after*
    import, which is why its isolation does not actually work.)
    """
    for name in list(sys.modules):
        if name == "roboviva" or name.startswith("roboviva."):
            del sys.modules[name]
    for name in ("config", "views", "flask_shelve"):
        sys.modules.pop(name, None)


class _PdfCounter(object):
    """Stands in for tex.latex2pdf, counting calls.

    handle_request calls latex2pdf twice per regeneration (views.py:87 and
    again at :102, discarding the first result), so the call count is itself a
    behavior worth pinning -- and running pdflatex for real twice per scenario
    would make the suite far too slow.
    """

    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail
        self.sources = []

    def __call__(self, src, **kwargs):
        self.calls += 1
        self.sources.append(src)
        if self.fail:
            raise ValueError("simulated pdflatex failure")
        return b"%PDF-1.4 stub\n%%EOF\n"


def op_http(args):
    """Drive the legacy Flask app through a scripted scenario.

    A scenario is a list of steps, each either an HTTP request or a state
    mutation (advancing the frozen clock, deleting a cached PDF). Everything
    the app touches is controlled: the clock, the cache directory, the shelve
    file, RideWithGPS, and pdflatex.
    """
    import shutil
    import tempfile
    import time as time_module

    scenario = args["steps"]
    workdir = tempfile.mkdtemp(prefix="roboviva-http-")
    cache_dir = os.path.join(workdir, "pdf_cache")
    if not args.get("no_cache_dir"):
        os.makedirs(cache_dir)

    _reset_app_modules()
    import config
    config.PDF_CACHE_DIR = cache_dir
    config.SHELVE_FILENAME = os.path.join(workdir, "shelf.db")

    # Frozen clock: /cache renders ages as text, so real time would make the
    # goldens unstable.
    clock = {"now": float(args.get("start_time", 1000000.0))}
    real_time = time_module.time
    time_module.time = lambda: clock["now"]

    net = ScriptedNet(args.get("script"))
    pdf = _PdfCounter(fail=args.get("pdf_fails", False))

    responses = []
    try:
        import roboviva
        import roboviva.tex
        roboviva.app.config["TESTING"] = True
        # TESTING=True normally makes Flask re-raise unhandled exceptions
        # instead of returning 500. That is convenient for debugging but would
        # record a Python traceback where a deployed app returns an error page,
        # so force the production behavior back on. views.purge_cache has an
        # unguarded os.stat that depends on this to become a real 500.
        roboviva.app.config["PROPAGATE_EXCEPTIONS"] = False
        if not args.get("real_pdf"):
            roboviva.tex.latex2pdf = pdf
            roboviva.views.roboviva.tex.latex2pdf = pdf

        client = roboviva.app.test_client()
        with net:
            for step in scenario:
                kind = step.get("do", "get")
                if kind == "advance_clock":
                    clock["now"] += step["seconds"]
                    responses.append({"advanced_to": clock["now"]})
                    continue
                if kind == "delete_pdf":
                    p = os.path.join(cache_dir, "%s.pdf" % step["route_id"])
                    existed = os.path.exists(p)
                    if existed:
                        os.unlink(p)
                    responses.append({"deleted": step["route_id"],
                                      "existed": existed})
                    continue

                method = step.get("method", "GET")
                resp = client.open(step["path"], method=method)
                body = resp.get_data()
                is_pdf = resp.headers.get("Content-Type", "").startswith(
                    "application/pdf")
                entry = {
                    "path": step["path"],
                    "method": method,
                    "status": resp.status_code,
                    "content_type": resp.headers.get("Content-Type"),
                    "location": resp.headers.get("Location"),
                    "content_disposition": resp.headers.get(
                        "Content-Disposition"),
                    "allow": resp.headers.get("Allow"),
                }
                if is_pdf:
                    entry["body_bytes"] = len(body)
                    entry["body_prefix"] = body[:5].decode("latin-1")
                else:
                    entry["body"] = body.decode("utf-8", "replace")
                responses.append(entry)
    finally:
        time_module.time = real_time
        shutil.rmtree(workdir, ignore_errors=True)
        _reset_app_modules()

    return {
        "responses": responses,
        "pdflatex_calls": pdf.calls,
        "rwgps_requests": net.requests,
    }


def op_cli(args):
    """Run make_latex.py / make_pdf.py as a subprocess.

    Genuinely out-of-process so argv handling, exit codes and stdout format are
    measured as a user would see them. The network stub cannot reach into a
    subprocess, so these scenarios use a sitecustomize shim that installs it.
    """
    import shutil
    import subprocess
    import tempfile

    workdir = tempfile.mkdtemp(prefix="roboviva-cli-")
    try:
        shim = os.path.join(workdir, "sitecustomize.py")
        with open(shim, "wb") as fh:
            fh.write(("""
import json, sys
sys.path.insert(0, %r)
sys.path.insert(0, %r)
from stub_net import ScriptedNet
_script = json.loads(open(%r).read())
ScriptedNet(_script).__enter__()
""" % (_HERE, _PKG, os.path.join(workdir, "script.json"))).encode("utf-8"))
        with open(os.path.join(workdir, "script.json"), "wb") as fh:
            fh.write(json.dumps(args.get("script") or []).encode("utf-8"))

        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [workdir, _HERE, _PKG, _REPO, env.get("PYTHONPATH", "")])

        proc = subprocess.Popen(
            ["python2", os.path.join(_REPO, args["script_name"])]
            + [str(a) for a in args.get("argv", [])],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=workdir, env=env)
        out, err = proc.communicate()
        produced = sorted(f for f in os.listdir(workdir)
                          if f.endswith(".pdf"))
        return {
            "returncode": proc.returncode,
            "stdout": out.decode("utf-8", "replace"),
            "stderr_tail": err.decode("utf-8", "replace").strip()
                                .splitlines()[-1:],
            "files_created": produced,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _fetch(fn, args):
    """Run a fetch function against a scripted network.

    Returns the requests that were made alongside the result, because half the
    contract is in the request: the literal `api_key=None`, the plain http://
    scheme, the 5s timeout, and whether If-None-Match was sent.
    """
    net = ScriptedNet(args.get("script"))
    kwargs = {}
    if args.get("etag") is not None:
        kwargs["etag"] = args["etag"]
    if "api_key" in args and fn is ridewithgps.getETagAndCuesheet_viaJSON:
        kwargs["api_key"] = args["api_key"]

    with net:
        try:
            etag, route = fn(args["route_id"], **kwargs)
            outcome = {
                "ok": True,
                "etag": etag,
                "route": route_to_dict(route) if route is not None else None,
            }
        except Exception as exc:
            outcome = {
                "ok": False,
                "error": {"type": type(exc).__name__,
                          "message": _safe_str(exc)},
            }
    outcome["requests"] = net.requests
    return outcome


def op_fetch_json(args):
    return _fetch(ridewithgps.getETagAndCuesheet_viaJSON, args)


def op_fetch_csv(args):
    return _fetch(ridewithgps.getETagAndCuesheet_viaCSV, args)


def op_render_pdf(args):
    """Render LaTeX and return a structural summary, never the raw bytes.

    PDFs are not byte-reproducible -- /ID and /CreationDate differ per run --
    so the golden is page count, page geometry and the extracted text layer.
    That is enough to catch a rendering regression (a dropped row, a lost
    glyph, a changed page size) without chasing nondeterminism.

    Extraction runs under python3/pypdf in this same image, and the py3 test
    suite uses the same pypdf version, so the extractor can never be the source
    of a difference.
    """
    import subprocess
    import tempfile

    src = args["latex"]
    if not isinstance(src, unicode):
        src = src.decode("utf-8")

    try:
        pdf = tex.latex2pdf(src)
    except Exception as exc:
        # A LaTeX failure is a legitimate golden: it is what the service does
        # for this input, and views.py turns it into the 0xFF error page.
        msg = _safe_str(exc)
        return {"rendered": False,
                "error_type": type(exc).__name__,
                "error_excerpt": _tex_error_excerpt(msg)}

    workdir = tempfile.mkdtemp(prefix="roboviva-pdf-")
    try:
        pdf_path = os.path.join(workdir, "out.pdf")
        with open(pdf_path, "wb") as fh:
            fh.write(pdf)
        summary = json.loads(subprocess.check_output(
            ["python3", os.path.join(_HERE, "pdf_summary.py"), pdf_path]))
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)

    summary["rendered"] = True
    summary["bytes_present"] = len(pdf) > 0
    summary["header"] = pdf[:5]
    summary["trailer"] = pdf[-6:]

    path = args.get("save_to")
    if path:
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with open(path, "wb") as fh:
            fh.write(pdf)
    return summary


def _tex_error_excerpt(log):
    """Pull the meaningful lines out of a texput.log dumped into an exception.

    tex.convert raises ValueError carrying the ENTIRE log (tex.py:148-150),
    which is thousands of lines of font paths. Only the actual error lines are
    stable enough to be a golden.
    """
    keep = []
    for line in log.splitlines():
        if line.startswith("!") or "Missing character" in line:
            if line not in keep:
                keep.append(line)
    return keep[:10]


OPS = {
    "ping": op_ping,
    "enums": op_enums,
    "escape": op_escape,
    "format_markup": op_format_markup,
    "instruction_to_latex": op_instruction_to_latex,
    "make_climb": op_make_climb,
    "entry_color": op_entry_color,
    "color_from_instruction": op_color_from_instruction,
    "clean_description": op_clean_description,
    "parse_custom_instruction": op_parse_custom_instruction,
    "instruction_str_to_cue": op_instruction_str_to_cue,
    "modifier_for": op_modifier_for,
    "entry_from_rwgps": op_entry_from_rwgps,
    "csv_rows_to_entries": op_csv_rows_to_entries,
    "adjust_start_and_end": op_adjust_start_and_end,
    "entry_repr": op_entry_repr,
    "route_repr": op_route_repr,
    "entry_to_latex_row": op_entry_to_latex_row,
    "make_latex": op_make_latex,
    "make_header": op_make_header,
    "latex_footer": op_latex_footer,
    "render_pdf": op_render_pdf,
    "fetch_json": op_fetch_json,
    "fetch_csv": op_fetch_csv,
    "http": op_http,
    "cli": op_cli,
}


def handle(req):
    op = req.get("op")
    if op not in OPS:
        return {"id": req.get("id"), "ok": False,
                "error": {"type": "UnknownOp", "message": str(op)}}
    try:
        return {"id": req.get("id"), "ok": True,
                "result": OPS[op](req.get("args") or {})}
    except Exception as exc:
        return {"id": req.get("id"), "ok": False, "error": {
            "type": type(exc).__name__,
            "message": _safe_str(exc),
            "traceback": traceback.format_exc().splitlines()[-4:],
        }}


def _safe_str(exc):
    try:
        return unicode(exc)
    except Exception:
        try:
            return str(exc).decode("utf-8", "replace")
        except Exception:
            return "<unprintable %s>" % type(exc).__name__


def main():
    # NOT `for line in sys.stdin`. Python 2's file iterator uses an internal
    # read-ahead buffer that blocks until the buffer fills or stdin hits EOF,
    # which deadlocks a request/response protocol over a pipe: the caller waits
    # for a reply that is stuck behind the read-ahead. readline() reads exactly
    # one line and returns.
    while True:
        line = sys.stdin.readline()
        if not line:          # EOF -- the caller closed stdin
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError as exc:
            resp = {"id": None, "ok": False,
                    "error": {"type": "BadRequest", "message": str(exc)}}
        else:
            resp = handle(req)
        sys.stdout.write(json.dumps(resp, ensure_ascii=True) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Run the corpus through the legacy code and write harness/golden/.

Runs INSIDE the oracle container, under python2, importing bridge.py so the
operations are literally the same ones `pytest --sut=legacy` exercises. There
is no second implementation to drift.

    harness/oracle/run.sh generate    # write goldens
    harness/oracle/run.sh verify      # regenerate to a temp dir and diff

Golden files are JSON with sorted keys and a trailing newline so that `git
diff` on a regenerated set is meaningful in review.
"""
import json
import os
import sys

import bridge  # noqa: E402  (adds the legacy package to sys.path on import)

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.normpath(os.path.join(HERE, ".."))
CORPUS = os.path.join(HARNESS, "corpus")

def _http_args(c):
    args = {"steps": c["steps"], "script": c["script"]}
    for opt in ("pdf_fails", "no_cache_dir", "real_pdf", "start_time"):
        if opt in c:
            args[opt] = c[opt]
    return args


def _fetch_args(c):
    """Fetch cases carry an optional api_key; everything else is uniform."""
    args = {"route_id": c["route_id"], "etag": c.get("etag"),
            "script": c["script"]}
    if "api_key" in c:
        args["api_key"] = c["api_key"]
    return args


# corpus file -> (bridge op, kwargs builder from the case dict)
STRING_SUITES = [
    ("strings/escape.json", "escape",
     lambda c: {"text": c["text"]}),
    ("strings/format.json", "format_markup",
     lambda c: {"text": c["text"]}),
    ("strings/clean_description.json", "clean_description",
     lambda c: {"description": c["description"]}),
    ("strings/parse_custom_instruction.json", "parse_custom_instruction",
     lambda c: {"description": c["description"]}),
    ("strings/instruction_str_to_cue.json", "instruction_str_to_cue",
     lambda c: {"instruction_str": c["instruction_str"]}),
    ("strings/color_from_instruction.json", "color_from_instruction",
     lambda c: {"instruction": c["instruction"]}),
    ("strings/instruction_to_latex.json", "instruction_to_latex",
     lambda c: {"instruction": c["instruction"], "modifier": c["modifier"]}),
    ("strings/entry_color.json", "entry_color",
     lambda c: {"color": c["color"]}),
    ("model/entry_repr.json", "entry_repr",
     lambda c: {"entry": c["entry"]}),
    ("model/route_repr.json", "route_repr",
     lambda c: {"route": c["route"]}),
    ("model/adjust_start_end.json", "adjust_start_and_end",
     lambda c: {"route": c["route"]}),
    ("rwgps/fetch_json.json", "fetch_json", _fetch_args),
    ("rwgps/parse_json.json", "fetch_json", _fetch_args),
    ("rwgps/approval.json", "fetch_json", _fetch_args),
    ("rwgps/fetch_csv.json", "fetch_csv", _fetch_args),
    ("latex/entry_rows.json", "entry_to_latex_row",
     lambda c: {"entry": c["entry"]}),
    ("http/endpoints.json", "http", _http_args),
    ("cli/scripts.json", "cli",
     lambda c: {"script_name": c["script_name"], "argv": c["argv"],
                "script": c["script"]}),
]


def load(relpath):
    with open(os.path.join(CORPUS, relpath), "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def dump(out_root, relpath, obj):
    path = os.path.join(out_root, relpath)
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        os.makedirs(d)
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)
    with open(path, "wb") as fh:
        fh.write(text.encode("utf-8"))
        fh.write(b"\n")
    return path


def run_case(op, kwargs):
    """Invoke a bridge op, recording either its value or its exception.

    An exception is a legitimate golden: several legacy paths raise, and the
    rewrite has to raise the same way.
    """
    try:
        return {"ok": True, "result": bridge.OPS[op](kwargs)}
    except Exception as exc:
        return {"ok": False, "error": {
            "type": type(exc).__name__,
            "message": bridge._safe_str(exc),
        }}


def generate_strings(out_root):
    written = []
    for relpath, op, build_args in STRING_SUITES:
        cases = load(relpath)
        results = []
        for c in cases:
            r = run_case(op, build_args(c))
            r["name"] = c["name"]
            results.append(r)
        written.append(dump(out_root, relpath, results))
        n_err = len([r for r in results if not r["ok"]])
        print("  %-46s %3d cases%s" % (
            relpath, len(results),
            (" (%d raise)" % n_err) if n_err else ""))
    return written


def generate_documents(out_root):
    """Write each whole-document case as a real .tex file.

    Not JSON: the LaTeX source is the byte-exact contract, and a reviewer
    should be able to read the diff as LaTeX and even compile it by hand. Cases
    that raise get an entry in the sidecar index instead of a file.
    """
    cases = load("latex/documents.json")
    index = []
    for c in cases:
        outcome = run_case("make_latex", {"route": c["route"]})
        if outcome["ok"]:
            rel = "latex/documents/%s.tex" % c["name"]
            path = os.path.join(out_root, rel)
            d = os.path.dirname(path)
            if not os.path.isdir(d):
                os.makedirs(d)
            with open(path, "wb") as fh:
                fh.write(outcome["result"].encode("utf-8"))
            index.append({"name": c["name"], "ok": True, "file": rel,
                          "bytes": len(outcome["result"].encode("utf-8"))})
        else:
            index.append({"name": c["name"], "ok": False,
                          "error": outcome["error"]})
    dump(out_root, "latex/documents.json", index)
    n_err = len([i for i in index if not i["ok"]])
    print("  %-46s %3d cases%s" % ("latex/documents.json", len(index),
                                   (" (%d raise)" % n_err) if n_err else ""))


def generate_pdfs(out_root):
    """Render every document case to PDF and record a structural summary.

    The slow phase -- each case shells out to pdflatex, twice, because
    tex.convert re-runs until texput.aux stabilizes.
    """
    cases = load("latex/documents.json")
    index = load("latex/documents.json")  # placeholder to keep names aligned
    results = []
    for c in cases:
        doc = run_case("make_latex", {"route": c["route"]})
        if not doc["ok"]:
            results.append({"name": c["name"], "ok": False,
                            "error": doc["error"], "stage": "make_latex"})
            continue
        out = run_case("render_pdf", {"latex": doc["result"]})
        if out["ok"]:
            results.append({"name": c["name"], "ok": True,
                            "result": out["result"]})
        else:
            results.append({"name": c["name"], "ok": False,
                            "error": out["error"], "stage": "render_pdf"})
    dump(out_root, "pdf/documents.json", results)
    n_fail = len([r for r in results if not r["ok"]])
    n_unrendered = len([r for r in results
                        if r["ok"] and not r["result"].get("rendered")])
    print("  %-46s %3d cases%s%s" % (
        "pdf/documents.json", len(results),
        (" (%d error)" % n_fail) if n_fail else "",
        (" (%d did not render)" % n_unrendered) if n_unrendered else ""))
    del index


def generate_approval(out_root):
    """The end-to-end tier: recorded fixture -> Route -> .tex -> PDF summary.

    This is the "does a real cue sheet still come out identical" check, and the
    one to watch during the rewrite.
    """
    cases = load("rwgps/approval.json")
    index = []
    for c in cases:
        fetched = run_case("fetch_json", _fetch_args(c))
        if not fetched["ok"] or not fetched["result"]["ok"]:
            index.append({"name": c["name"], "ok": False, "stage": "fetch",
                          "error": fetched.get("error")
                          or fetched["result"]["error"]})
            continue
        route = fetched["result"]["route"]
        doc = run_case("make_latex", {"route": route})
        if not doc["ok"]:
            index.append({"name": c["name"], "ok": False, "stage": "make_latex",
                          "error": doc["error"]})
            continue
        rel = "approval/%s.tex" % c["name"]
        dump_text(out_root, rel, doc["result"])
        pdf = run_case("render_pdf", {"latex": doc["result"]})
        entry = {"name": c["name"], "ok": True, "tex": rel,
                 "route_id": c["route_id"],
                 "entry_count": len(route["entries"]),
                 "route_name": route["name"],
                 "length_mi": route["length_mi"],
                 "elevation_gain_ft": route["elevation_gain_ft"]}
        entry["pdf"] = pdf["result"] if pdf["ok"] else {"error": pdf["error"]}
        index.append(entry)
    dump(out_root, "approval/index.json", index)
    n_fail = len([i for i in index if not i["ok"]])
    print("  %-46s %3d routes%s" % ("approval/index.json", len(index),
                                    (" (%d failed)" % n_fail) if n_fail else ""))


def dump_text(out_root, relpath, text):
    path = os.path.join(out_root, relpath)
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "wb") as fh:
        fh.write(text.encode("utf-8"))


def generate_env(out_root):
    """Record the environment the goldens were produced in.

    If a golden ever changes, the first question is whether the code changed or
    the toolchain did. This answers it.
    """
    import subprocess
    try:
        pdftex = subprocess.check_output(
            ["pdflatex", "--version"]).decode("utf-8").splitlines()[0]
    except Exception as exc:
        pdftex = "unavailable: %s" % exc
    env = {
        "python": sys.version.replace("\n", " "),
        "default_encoding": sys.getdefaultencoding(),
        "pdflatex": pdftex,
        "enums": bridge.OPS["enums"]({}),
    }
    dump(out_root, "environment.json", env)
    print("  %-46s" % "environment.json")


def main(argv):
    out_root = argv[1] if len(argv) > 1 else os.path.join(HARNESS, "golden")
    only = argv[2] if len(argv) > 2 else None
    print("writing goldens to %s" % out_root)
    generate_env(out_root)
    generate_strings(out_root)
    generate_documents(out_root)
    # The PDF phases shell out to pdflatex for every case and take minutes, so
    # they can be skipped while iterating on the cheap ones.
    if only != "fast":
        generate_pdfs(out_root)
        generate_approval(out_root)
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

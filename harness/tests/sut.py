"""The parity contract.

Every operation the harness exercises goes through this module, so the same
test suite can run against two very different systems:

    ROBOVIVA_SUT=legacy   the Python 2 code, over a stdio JSON bridge into the
                          oracle container. Used to prove the harness is green
                          against the original before any rewrite exists.
    ROBOVIVA_SUT=new      the rewrite (default).

Values cross the boundary as plain JSON, so the rewrite is free to use
dataclasses, enums, pydantic -- anything -- as long as it can satisfy the
`NewBackend` shim below.

A cue entry is a dict:
    {instruction, description, absolute_distance, note, modifier,
     for_distance, color}
A route is a dict:
    {name, id, entries, elevation_gain_ft, length_mi}
An RWGPS entry is a dict:
    {instruction_str, description_str, absolute_distance,
     prev_absolute_distance, next_absolute_distance, note_str}
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
from typing import Any


REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", ".."))
ORACLE_IMAGE = os.environ.get("ROBOVIVA_ORACLE_IMAGE", "roboviva-oracle:latest")


class SutError(Exception):
    """Raised when the system under test reports a failure.

    Carries the original exception type so tests can assert on it -- a legacy
    KeyError has to stay a KeyError, not become a generic failure.
    """

    def __init__(self, type_name: str, message: str, traceback_tail=None):
        super().__init__("%s: %s" % (type_name, message))
        self.type_name = type_name
        self.message = message
        self.traceback_tail = traceback_tail or []


class LegacyBackend:
    """Drives harness/oracle/bridge.py inside the container.

    One long-lived container per session: starting python2 and importing the
    legacy modules costs more than the calls themselves, and the corpus makes
    thousands of calls.
    """

    def __init__(self, image: str = ORACLE_IMAGE):
        self.image = image
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._next_id = 0

    def _ensure(self) -> subprocess.Popen:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        # stderr goes to a file, NOT subprocess.PIPE. Nothing drains a stderr
        # pipe during a run, so once the OS buffer (~64KB) fills, the bridge
        # blocks on write and the whole suite deadlocks -- which it did, only
        # on full runs, because no single test file produced enough output.
        self._stderr = tempfile.TemporaryFile()
        self._proc = subprocess.Popen(
            ["docker", "run", "--rm", "-i",
             "--network", "none",          # the bridge must never reach out
             # SELinux hosts (Fedora/RHEL) deny bind-mount reads without this.
             # ':z' would work too but relabels the user's working tree.
             "--security-opt", "label=disable",
             "--user", "%d:%d" % (os.getuid(), os.getgid()),
             "-v", "%s:/repo:ro" % REPO,
             "-w", "/repo",
             "-e", "HOME=/tmp",
             "-e", "PYTHONHASHSEED=0",
             "-e", "SOURCE_DATE_EPOCH=0",
             "-e", "FORCE_SOURCE_DATE=1",
             self.image,
             "-c", "exec python2 /repo/harness/oracle/bridge.py"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr,
        )
        return self._proc

    def call(self, op: str, **args: Any) -> Any:
        with self._lock:
            proc = self._ensure()
            self._next_id += 1
            req = {"id": self._next_id, "op": op, "args": args}
            assert proc.stdin and proc.stdout
            proc.stdin.write((json.dumps(req) + "\n").encode("utf-8"))
            proc.stdin.flush()
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError(
                    "legacy bridge died during op %r:\n%s"
                    % (op, self._read_stderr()))
            resp = json.loads(line.decode("utf-8"))
        if not resp.get("ok"):
            e = resp.get("error") or {}
            raise SutError(e.get("type", "Unknown"), e.get("message", ""),
                           e.get("traceback"))
        return resp.get("result")

    def _read_stderr(self) -> str:
        try:
            self._stderr.seek(0)
            return self._stderr.read().decode("utf-8", "replace")[-4000:]
        except Exception:
            return "<stderr unavailable>"

    def close(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            try:
                assert self._proc.stdin
                self._proc.stdin.close()
                self._proc.wait(timeout=10)
            except Exception:
                self._proc.kill()
        self._proc = None


class NewBackend:
    """Dispatches to the rewrite.

    Deliberately unimplemented: until the rewrite exists, every parity test
    fails loudly with a message naming the operation that is missing. That is
    the TDD target, and a skipped test would hide it.
    """

    def call(self, op: str, **args: Any) -> Any:
        raise NotImplementedError(
            "the rewrite does not implement %r yet. Run the suite against the "
            "legacy oracle with --sut=legacy to verify the harness itself." % op)

    def close(self) -> None:
        pass


_BACKENDS = {"legacy": LegacyBackend, "new": NewBackend}


def make_backend(name: str):
    try:
        return _BACKENDS[name]()
    except KeyError:
        raise SystemExit("unknown --sut=%r; expected one of %s"
                         % (name, ", ".join(sorted(_BACKENDS))))


class Sut:
    """Typed facade over a backend. This is what tests import."""

    def __init__(self, backend):
        self._b = backend

    # -- introspection ----------------------------------------------------
    def ping(self) -> dict:
        return self._b.call("ping")

    def enums(self) -> dict:
        return self._b.call("enums")

    # -- latex.py ---------------------------------------------------------
    def escape(self, text: str) -> str:
        return self._b.call("escape", text=text)

    def format_markup(self, text: str) -> str:
        return self._b.call("format_markup", text=text)

    def instruction_to_latex(self, instruction: str, modifier: str) -> str:
        return self._b.call("instruction_to_latex",
                            instruction=instruction, modifier=modifier)

    def make_climb(self, climb_type: str) -> str:
        return self._b.call("make_climb", climb_type=climb_type)

    def entry_color(self, color: str):
        return self._b.call("entry_color", color=color)

    def entry_to_latex_row(self, entry: dict) -> str:
        return self._b.call("entry_to_latex_row", entry=entry)

    def make_latex(self, route: dict) -> str:
        return self._b.call("make_latex", route=route)

    def make_header(self, route: dict) -> str:
        return self._b.call("make_header", route=route)

    def latex_footer(self) -> str:
        return self._b.call("latex_footer")

    # -- cue.py / cue_utils.py --------------------------------------------
    def color_from_instruction(self, instruction: str) -> str:
        return self._b.call("color_from_instruction", instruction=instruction)

    def adjust_start_and_end(self, route: dict) -> dict:
        return self._b.call("adjust_start_and_end", route=route)

    def entry_repr(self, entry: dict) -> str:
        return self._b.call("entry_repr", entry=entry)

    def route_repr(self, route: dict) -> str:
        return self._b.call("route_repr", route=route)

    # -- ridewithgps.py ---------------------------------------------------
    def clean_description(self, description: str) -> str:
        return self._b.call("clean_description", description=description)

    def parse_custom_instruction(self, description: str):
        return self._b.call("parse_custom_instruction", description=description)

    def instruction_str_to_cue(self, instruction_str: str) -> str:
        return self._b.call("instruction_str_to_cue",
                            instruction_str=instruction_str)

    def modifier_for(self, entry: dict, quick_threshold_mi=None) -> str:
        return self._b.call("modifier_for", entry=entry,
                            quick_threshold_mi=quick_threshold_mi)

    def entry_from_rwgps(self, entry: dict) -> dict:
        return self._b.call("entry_from_rwgps", entry=entry)

    def csv_rows_to_entries(self, rows: list, encode_utf8: bool = False) -> list:
        return self._b.call("csv_rows_to_entries", rows=rows,
                            encode_utf8=encode_utf8)

    def fetch_json(self, route_id, etag=None, script=None,
                   api_key="__unset__") -> dict:
        """Fetch a route against a scripted network.

        `api_key` defaults to the sentinel "__unset__" rather than None so a
        case can distinguish "do not pass api_key at all" (letting the legacy
        default apply, which is what production does) from "pass an explicit
        value". Passing None explicitly would be indistinguishable from the
        default and would hide the whole api_key=None question.
        """
        args = {"route_id": route_id, "etag": etag, "script": script or []}
        if api_key != "__unset__":
            args["api_key"] = api_key
        return self._b.call("fetch_json", **args)

    def fetch_csv(self, route_id, etag=None, script=None) -> dict:
        return self._b.call("fetch_csv", route_id=route_id, etag=etag,
                            script=script or [])

    # -- views.py (whole-app scenarios) -----------------------------------
    def http(self, steps: list, script: list | None = None,
             pdf_fails: bool = False, no_cache_dir: bool = False,
             real_pdf: bool = False) -> dict:
        return self._b.call("http", steps=steps, script=script or [],
                            pdf_fails=pdf_fails, no_cache_dir=no_cache_dir,
                            real_pdf=real_pdf)

    # -- CLI scripts ------------------------------------------------------
    def cli(self, script_name: str, argv: list,
            script: list | None = None) -> dict:
        return self._b.call("cli", script_name=script_name, argv=argv,
                            script=script or [])

    # -- tex.py -----------------------------------------------------------
    def render_pdf(self, latex_src: str, save_to: str | None = None) -> dict:
        return self._b.call("render_pdf", latex=latex_src, save_to=save_to)

    def close(self) -> None:
        self._b.close()

#!/usr/bin/env python3
"""Validate the documentation against the code it describes.

Two checks, both cheap enough to run in CI:

  1. Every `file.py:line` citation points at a line that exists.
  2. Every relative markdown link resolves to a real file.

Citations rot the moment code moves, and a doc full of stale line numbers is
worse than one with none -- it teaches the reader to distrust it.

    python3 docs/check_docs.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, ".."))

# "views.py:147-155", "cue.py:53", "harness/oracle/bridge.py"
CITATION = re.compile(r"\b([\w./-]+\.py):(\d+)(?:-(\d+))?\b")
LINK = re.compile(r"\[[^\]]*\]\(([^)#][^)]*)\)")

# Cited bare filenames resolve against these, in order.
SEARCH_DIRS = ["", "roboviva", "harness", "harness/oracle", "harness/tests",
               "harness/corpus", "docs"]


def resolve(path):
    for d in SEARCH_DIRS:
        candidate = os.path.join(REPO, d, path)
        if os.path.isfile(candidate):
            return candidate
    return None


def line_count(path):
    with open(path, "rb") as fh:
        return sum(1 for _ in fh)


def check(md_path):
    problems = []
    with open(md_path, encoding="utf-8") as fh:
        text = fh.read()
    rel_md = os.path.relpath(md_path, REPO)

    for match in CITATION.finditer(text):
        filename, start, end = match.group(1), int(match.group(2)), match.group(3)
        target = resolve(filename)
        if target is None:
            problems.append("%s: cites unknown file %s" % (rel_md, filename))
            continue
        n = line_count(target)
        for lineno in filter(None, [start, int(end) if end else None]):
            if lineno > n:
                problems.append(
                    "%s: cites %s:%d but that file has %d lines"
                    % (rel_md, filename, lineno, n))

    for match in LINK.finditer(text):
        href = match.group(1).strip()
        if href.startswith(("http://", "https://", "mailto:")):
            continue
        # "other.md#some-heading" -> check the file AND that the anchor exists.
        path_part, _, anchor = href.partition("#")
        target = os.path.normpath(
            os.path.join(os.path.dirname(md_path), path_part))
        if not os.path.exists(target):
            problems.append("%s: broken link -> %s" % (rel_md, href))
            continue
        if anchor and target.endswith(".md"):
            if anchor not in heading_slugs(target):
                problems.append(
                    "%s: link -> %s but no such heading in %s"
                    % (rel_md, href, os.path.basename(target)))

    return problems


def heading_slugs(md_path):
    """GitHub-style anchor slugs for every heading in a markdown file.

    Lowercase, punctuation dropped, spaces to hyphens -- close enough to
    GitHub's algorithm for the headings these documents actually use.
    """
    slugs = set()
    with open(md_path, encoding="utf-8") as fh:
        for line in fh:
            if not line.startswith("#"):
                continue
            title = line.lstrip("#").strip()
            slug = re.sub(r"[^\w\s-]", "", title.lower())
            slugs.add(re.sub(r"[\s_]+", "-", slug).strip("-"))
    return slugs


def main():
    docs = sorted(f for f in os.listdir(HERE) if f.endswith(".md"))
    all_problems = []
    for name in docs:
        found = check(os.path.join(HERE, name))
        status = "OK" if not found else "%d problem(s)" % len(found)
        print("  %-28s %s" % (name, status))
        all_problems.extend(found)

    if all_problems:
        print("\n%d problem(s):" % len(all_problems), file=sys.stderr)
        for p in all_problems:
            print("  " + p, file=sys.stderr)
        return 1
    print("\nall citations resolve, all links valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())

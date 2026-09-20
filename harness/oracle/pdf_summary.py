#!/usr/bin/env python3
"""Summarize a PDF into something stable enough to be a golden.

Runs under python3 inside the oracle image, using the same pypdf version the
py3 test suite has, so the extractor itself can never be the reason two
summaries differ.

Deliberately excluded: /ID, /CreationDate, /Producer, byte length, and object
offsets. All of them change between runs of the same input, so asserting on
them would produce a permanently red suite.

    python3 pdf_summary.py <file.pdf>   ->  JSON on stdout
"""
import json
import re
import sys

from pypdf import PdfReader


def normalize(text):
    """Collapse whitespace so line-breaking differences do not register.

    pdflatex decides where to break lines inside a table cell, and that can
    shift with unrelated changes. The words and their order are the signal;
    the exact spacing is not.
    """
    return re.sub(r"\s+", " ", text).strip()


def summarize(path):
    reader = PdfReader(path)
    pages = []
    for page in reader.pages:
        box = page.mediabox
        pages.append({
            # Rounded to whole points: letter paper is 612x792 and floating
            # point noise in the box is not meaningful.
            "width_pt": round(float(box.width)),
            "height_pt": round(float(box.height)),
            "text": normalize(page.extract_text() or ""),
        })
    return {"page_count": len(pages), "pages": pages}


if __name__ == "__main__":
    json.dump(summarize(sys.argv[1]), sys.stdout, sort_keys=True)

#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os
import re
import sys

import practice_bank_loader as pbl


ALLOWED_DIFFS = {"easy", "medium", "hard"}

WARN_PATTERNS = [
    (re.compile(r"\bopen\s*\(", re.I), "uses open(); OK for file-I/O topic"),
    (re.compile(r"\bargparse\b|\bsys\.argv\b", re.I), "CLI topic; ensure tests simulate argv"),
]

FAIL_PATTERNS = [
    (re.compile(r"\bmicropip\b|\bsubprocess\b", re.I), "disallowed in browser runner"),
    (re.compile(r"__import__\s*\(|\beval\s*\(|\bexec\s*\(", re.I), "disallowed dynamic code"),
]


def main() -> int:
    # ensure we validate everything (including generated)
    os.environ["PRACTICE_INCLUDE_GENERATED"] = "1"
    pbl.load_practice_bank.cache_clear()

    problems = pbl.load_practice_bank()
    if not problems:
        print("No problems found.")
        return 1

    errors: list[str] = []
    warns: list[str] = []

    seen = set()
    for p in problems:
        # unique slug
        if p.slug in seen:
            errors.append(f"duplicate slug: {p.slug}")
        seen.add(p.slug)

        # basic shape
        parts = p.slug.split("/")
        if len(parts) < 3:
            errors.append(f"{p.slug}: slug should look like topic/difficulty/name")
        if p.difficulty not in ALLOWED_DIFFS:
            errors.append(f"{p.slug}: invalid difficulty {p.difficulty!r}")

        # required fields
        if not (p.title or "").strip():
            errors.append(f"{p.slug}: missing title")
        if not (p.prompt or "").strip():
            errors.append(f"{p.slug}: missing prompt")
        if not (p.starter_code or "").strip():
            errors.append(f"{p.slug}: missing starter_code")
        if not (p.tests or "").strip():
            errors.append(f"{p.slug}: missing tests")

        # tab safety (pyodide hates tabs)
        if "\t" in p.starter_code:
            errors.append(f"{p.slug}: starter_code contains TABs")
        if "\t" in p.tests:
            errors.append(f"{p.slug}: tests contains TABs")

        # at least one assert
        if "assert" not in p.tests:
            errors.append(f"{p.slug}: tests has no 'assert'")

        # compile check (syntax)
        try:
            compile(p.starter_code, f"<starter:{p.slug}>", "exec")
        except SyntaxError as e:
            errors.append(f"{p.slug}: starter_code SyntaxError: {e}")

        try:
            compile(p.tests, f"<tests:{p.slug}>", "exec")
        except SyntaxError as e:
            errors.append(f"{p.slug}: tests SyntaxError: {e}")

        try:
            compile(p.starter_code + "\n\n" + p.tests, f"<combined:{p.slug}>", "exec")
        except SyntaxError as e:
            errors.append(f"{p.slug}: combined SyntaxError: {e}")

        # pattern checks
        combined = (p.starter_code or "") + "\n" + (p.tests or "")
        for rx, msg in FAIL_PATTERNS:
            if rx.search(combined):
                errors.append(f"{p.slug}: {msg}")
        for rx, msg in WARN_PATTERNS:
            if rx.search(combined):
                warns.append(f"{p.slug}: warning: {msg}")

    for w in warns[:50]:
        print("WARN:", w)
    if len(warns) > 50:
        print(f"WARN: ... {len(warns)-50} more warnings")

    if errors:
        for e in errors[:80]:
            print("ERROR:", e)
        if len(errors) > 80:
            print(f"ERROR: ... {len(errors)-80} more errors")
        return 1

    print(f"OK: {len(problems)} problems validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


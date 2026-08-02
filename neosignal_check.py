#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check a codebase against models that have gone away.

    python neosignal_check.py .
    python neosignal_check.py src/ --json
    python neosignal_check.py . --quiet     # CI: say nothing unless something is wrong

Exit codes are the point of this existing at all:

    0   nothing you call is going away
    1   something you call is GONE, or shuts down inside 30 days
    2   could not check - network, or the service is down

so it drops into CI as a step that fails a build before a model does.

WHY THIS EXISTS
A deprecation calendar can only list what a vendor announced. Every tracker in
this space is built that way and says so - aimodelwatch.dev states its data is
"sourced from official deprecation pages". That is a real service and it has a
blind spot it cannot close by trying harder: a model that is simply gone one
morning was never on anybody's calendar, because nobody published a date for it.

This checks against a catalogue that is diffed every day. Of the model removals
it has recorded so far, ALL of them vanished with no end-of-life date ever
published. Those are exactly the ones a calendar cannot warn you about, and
exactly the ones that break a running product without notice.

NO KEY, NO SIGNUP, NO ACCOUNT. It reads two public JSON files.

IT READS BOTH SPELLINGS
`openai/gpt-5.2-chat` is the OpenRouter form. If you call a vendor SDK directly
you write `gpt-5.2-chat`, and both are matched - a bare name is resolved only
when it maps to exactly one model in the catalogue, so a suffix two vendors
share is skipped rather than guessed at.

HOW IT AVOIDS CRYING WOLF
It does not guess what a model id looks like. Every candidate token is kept
only if it matches a real id, so `utils/helpers`, `read-timeout-30` and
`on-click-handler` cannot survive. A bare name must also be at least six
characters and contain a digit. A false positive would require a variable
named exactly after a real model.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request

SITE = "https://neosignal-ai.vercel.app"
MODELS_URL = SITE + "/api/models.json"
CHANGES_URL = SITE + "/api/changes.json"

# Text files worth reading. Binary and vendored trees are skipped outright -
# scanning node_modules finds every model id in the world and none of them yours.
READ_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".go", ".rs",
            ".rb", ".java", ".kt", ".cs", ".php", ".swift", ".sh", ".yaml",
            ".yml", ".toml", ".json", ".env", ".ini", ".cfg", ".md", ".txt"}
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist",
             "build", "target", ".next", ".nuxt", "vendor", "site-packages",
             ".mypy_cache", ".pytest_cache", ".terraform"}

# `anthropic/claude-fable-5:batch`, `openai/gpt-5.1-codex`, `z-ai/glm-5.2`
CANDIDATE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._:-]*")

# The prefixed form is an OpenRouter convention. Anyone calling a vendor SDK
# directly writes the BARE name - `gpt-5.2-chat`, not `openai/gpt-5.2-chat` -
# and matching only the prefixed form made this tool blind to most of the code
# it is meant to help. Bare names are matched too, under three conditions that
# keep it from crying wolf:
#
#   - the name must resolve to EXACTLY ONE model in the catalogue, so a suffix
#     two vendors share is skipped rather than guessed at
#   - at least 6 characters, so short ids like `o1` cannot collide with a
#     variable name
#   - must contain a digit, which every real model id does and most English
#     words do not
BARE = re.compile(r"[A-Za-z][A-Za-z0-9._]*(?:-[A-Za-z0-9._]+)+")
BARE_MIN_LEN = 6

SHUTDOWN_SOON_DAYS = 30

# A string that appears in this file and nowhere a user would write it, used
# to recognise any copy of this script during a scan.
SELF_MARK = "neosignal-check/1.0"


def money(v):
    if v is None:
        return "?"
    return ("$%.2f" % v) if v >= 0.10 else ("$%.3f" % v)


def fetch(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "neosignal-check/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def walk(root: str):
    if os.path.isfile(root):
        yield root
        return
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            if os.path.splitext(name)[1].lower() in READ_EXT:
                yield os.path.join(base, name)


def bare_index(known: set) -> dict:
    """Unambiguous bare names -> the full id they mean.

    A suffix claimed by two vendors is dropped, not guessed. Being silent about
    an ambiguous name costs a finding; naming the wrong vendor's model costs
    trust, and this product has nothing else to trade on.
    """
    counts, first = {}, {}
    for mid in known:
        tail = mid.split("/", 1)[-1]
        if len(tail) < BARE_MIN_LEN or not any(c.isdigit() for c in tail):
            continue
        counts[tail] = counts.get(tail, 0) + 1
        first.setdefault(tail, mid)
    return {t: first[t] for t, n in counts.items() if n == 1}


def scan(root: str, known: set, bare: dict) -> dict:
    """Model ids you actually reference -> the files that reference them.

    Skips its own file. The intended way to run this is to curl it into the
    directory you want checked, and its documentation names real model ids as
    examples - so without this it reports three models from its own comments
    and the user has to work out which findings are about their code.
    """
    self_path = os.path.abspath(__file__)
    found = {}
    for path in walk(root):
        if os.path.abspath(path) == self_path:
            continue
        try:
            with io.open(path, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except (OSError, ValueError):
            continue
        # Skip ANY copy of this script, not only the one being executed. The
        # documented usage curls it into the directory under test, so a second
        # copy sitting there is normal - and its own documentation names real
        # model ids as examples, which would be reported as the user's.
        if SELF_MARK in text:
            continue
        rel = os.path.relpath(path, root) if os.path.isdir(root) else path
        hits = {t for t in CANDIDATE.findall(text) if t in known}
        # Only look for bare names where the prefixed form did not already
        # match on this line's id, so a file using the full form is not
        # reported twice under two spellings.
        for t in BARE.findall(text):
            mid = bare.get(t)
            if mid and mid not in hits:
                hits.add(mid)
        for token in hits:
            found.setdefault(token, set()).add(rel)
    return {k: sorted(v) for k, v in found.items()}


def verdict(mid: str, models: dict, changes: dict) -> tuple:
    """(level, headline, replacement) for one model.

    level: gone | soon | moved | ok. The replacement is returned as DATA rather
    than folded into the headline: the first version embedded it in the prose
    with a newline and nine spaces of indentation, which read fine in a terminal
    and put terminal layout inside the --json `detail` field, where a consumer
    would have to parse it back out.
    """
    rows = changes.get(mid) or []
    if mid not in models:
        gone = [r for r in rows if r.get("type") == "MODEL_REMOVED"]
        when = gone[0].get("date") if gone else None
        line = ("GONE from the catalogue%s, with no end-of-life date ever published"
                % (" on " + when if when else ""))
        # Where to go, when the data supports naming one. It often does not,
        # and the absence of a suggestion is itself information: nothing in
        # that vendor's remaining line-up is a defensible match. Better than
        # inventing one - the rule behind this was wrong four times before it
        # learned to stay quiet.
        move = next((r.get("replacement") for r in gone if r.get("replacement")), None)
        return ("gone", line, move)

    eol = (models[mid] or {}).get("expiration_date")
    if eol:
        left = [r.get("days_left") for r in rows
                if r.get("type") == "DEPRECATION_DEADLINE" and r.get("days_left") is not None]
        days = min(left) if left else None
        if days is not None and days <= SHUTDOWN_SOON_DAYS:
            return ("soon", "shuts down %s - %d days left" % (eol, days), None)
        return ("moved", "shuts down %s" % eol, None)

    priced = [r for r in rows if r.get("type") == "PRICING_CHANGE"]
    if priced:
        d = priced[0].get("delta") or {}
        out = d.get("completion") or {}
        if out.get("pct") is not None:
            return ("moved", "price moved %+.0f%% on output since %s"
                    % (out["pct"], priced[0].get("date") or "recently"), None)
        return ("moved", "price changed since %s" % (priced[0].get("date") or "recently"), None)
    return ("ok", "no change recorded", None)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Check a codebase for AI models that are gone or going away.")
    ap.add_argument("path", nargs="?", default=".", help="file or directory to scan")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--quiet", action="store_true",
                    help="print nothing when everything is fine (for CI)")
    args = ap.parse_args()

    # Fetch, then normalise the dict-or-list shape once. The catalogue stores
    # models keyed by id; a list is accepted too so a future shape change does
    # not silently report a clean scan.
    # BOTH are required, and the change record is the one that carries this
    # tool's whole reason to exist. A first draft treated it as optional
    # enrichment; a test on a project calling three removed models reported a
    # clean pass, because a model that is GONE is by definition absent from the
    # catalogue - the change record is the only place its id still exists. With
    # it missing the scanner cannot match what it is supposed to find and says
    # "nothing is going away" about a codebase full of dead calls, which is
    # worse than not running at all.
    try:
        raw = fetch(MODELS_URL).get("models") or {}
        changes = fetch(CHANGES_URL).get("changes") or {}
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError) as exc:
        sys.stderr.write("could not reach %s (%s)\n"
                         "nothing was checked - this is NOT a pass\n" % (SITE, exc))
        return 2

    if isinstance(raw, dict):
        models = {}
        for mid, rec in raw.items():
            if isinstance(rec, dict):
                models[mid] = rec
    else:
        models = {m.get("id"): m for m in raw if isinstance(m, dict) and m.get("id")}

    known = set(models) | set(changes)
    used = scan(args.path, known, bare_index(known))

    results = []
    for mid in sorted(used):
        level, why, move = verdict(mid, models, changes)
        row = {"model": mid, "level": level, "detail": why, "files": used[mid]}
        if move:
            row["replacement"] = move
        results.append(row)

    bad = [r for r in results if r["level"] in ("gone", "soon")]

    if args.json:
        print(json.dumps({"scanned": args.path, "models_referenced": len(results),
                          "action_required": len(bad), "results": results},
                         ensure_ascii=False, indent=1))
        return 1 if bad else 0

    if not results:
        if not args.quiet:
            print("No model ids from the catalogue appear in %s." % args.path)
            print("That is either a clean bill or the wrong directory - it does not")
            print("guess, so a model it has never seen is not reported.")
        return 0

    if bad or not args.quiet:
        print("%d model%s referenced in %s\n"
              % (len(results), "" if len(results) == 1 else "s", args.path))

    for r in results:
        if args.quiet and r["level"] not in ("gone", "soon"):
            continue
        mark = {"gone": "GONE ", "soon": "SOON ", "moved": "moved", "ok": "ok   "}[r["level"]]
        print("  %s  %-46s %s" % (mark, r["model"], r["detail"]))
        move = r.get("replacement")
        if move:
            print("         nearest still listed: %s at %s per million output, "
                  "against the %s it cost"
                  % (move["model"], money(move.get("price_per_million_output")),
                     money(move.get("gone_price_per_million_output"))))
        if r["level"] in ("gone", "soon"):
            for f in r["files"][:4]:
                print("         %s" % f)

    if bad:
        print("\n%d need%s attention. Full history: %s/gone.html"
              % (len(bad), "s" if len(bad) == 1 else "", SITE))
        return 1
    if not args.quiet:
        print("\nNothing you call is going away.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check a codebase against models that have gone away.

    python neosignal_check.py .
    python neosignal_check.py src/ --json
    python neosignal_check.py . --quiet     # CI: say nothing unless something is wrong

Exit codes are the point of this existing at all:

    0   nothing checked here has a change or a date against it
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
it has recorded so far, ALL of them vanished with no end-of-life date in the
catalogue beforehand. Those are exactly the ones a calendar cannot warn you
about, and exactly the ones that break a running product without notice.

AND THE OTHER DIRECTION
A vendor can publish a retirement date the catalogue never carries. Measured
2026-08-03: Anthropic publishes 2026-08-05 for claude-opus-4.1 and the
catalogue holds no date for it or its sixteen siblings, so this reported "no
change recorded" for a model with two days left. Vendor deprecation pages are
read directly now and merged into the same change record, which is why a
warning can say the vendor retires something the catalogue still lists.

NO KEY, NO SIGNUP, NO ACCOUNT. It reads two public JSON files.

IT READS THREE SPELLINGS
`openai/gpt-5.2-chat` is the OpenRouter form; a vendor SDK takes the bare
`gpt-5.2-chat`; and a vendor's own dated pin looks like
`claude-haiku-4-5-20251001`. All three resolve, each only where it lands on
exactly one model, so a suffix two vendors share is skipped rather than
guessed at.

WHERE IT LOOKS
Source in most languages, plus the places a model id actually hides: Jupyter
notebooks, Dockerfiles, Makefiles, Terraform, Gradle, and config of every
shape. An earlier version filtered on extension alone and found NONE of those
four - and then printed "either a clean bill or the wrong directory", which
reads as a pass. A missed model is worse than no tool, because the tool was
trusted.

HOW IT AVOIDS CRYING WOLF
It does not guess what a model id looks like. Every candidate token is kept
only if it matches a real id, so `utils/helpers`, `read-timeout-30` and
`on-click-handler` cannot survive. A bare name must also be at least six
characters and contain a digit. A false positive would require a variable
named exactly after a real model.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
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
            ".yml", ".toml", ".json", ".env", ".ini", ".cfg", ".md", ".txt",
            # Measured 2026-08-02 against the places real projects actually put
            # a model id: a Jupyter notebook, a Dockerfile, a Terraform
            # variable and a Makefile. The tool found NONE of the four and
            # printed "either a clean bill or the wrong directory", which reads
            # as a pass to someone whose entire model config lives in a
            # Dockerfile. A missed model is worse than no tool, because the
            # tool was trusted.
            ".ipynb", ".tf", ".tfvars", ".hcl", ".sql", ".gradle", ".properties",
            ".vue", ".svelte", ".astro", ".scala", ".clj", ".ex", ".exs",
            ".dart", ".lua", ".r", ".jl", ".tpl", ".j2", ".jinja", ".conf",
            ".xml", ".gitlab-ci.yml", ".tf.json"}

# Files with no extension at all, matched on name. An extension filter cannot
# see a Dockerfile.
READ_NAMES = {"dockerfile", "makefile", "procfile", "justfile", "rakefile",
              "containerfile", "jenkinsfile", "brewfile", "vagrantfile"}
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist",
             "build", "target", ".next", ".nuxt", "vendor", "site-packages",
             ".mypy_cache", ".pytest_cache", ".terraform",
             # Named explicitly because the blanket "skip anything starting
             # with a dot" that used to stand in for this list also skipped
             # .github - so a model pinned in a workflow was invisible, in the
             # one directory this tool's own README tells people to run it
             # from. Skipping is now a decision per directory, not a rule about
             # the first character.
             ".idea", ".vscode", ".cache", ".tox", ".gradle", ".svn", ".hg",
             ".bundle", ".yarn", ".pnpm-store", ".turbo", ".parcel-cache",
             ".serverless", ".vercel", ".netlify", ".angular", ".svelte-kit"}

# `.env`, `.env.local`, `.env.example`. A prefix test, because
# os.path.splitext(".env") returns (".env", "") - a leading dot belongs to the
# NAME, not to an extension - so the ".env" entry in READ_EXT above had never
# once matched a file actually called .env, and ".env.example" resolved to an
# extension of ".example". The intent was recorded and silently did nothing.
# Only the path and the model id are ever reported; contents are never printed.
ENV_PREFIX = ".env"

# A model id is written by a person, and people write small files. Measured
# 2026-08-03 against a real 391,000-file repository: the walk selected 21,590
# files totalling 1,490 MB and the scan did not finish in ten minutes. Capping
# at a megabyte keeps 97.3% of the files and 34% of the bytes, because what it
# drops is minified bundles and generated data - and a model id inside a bundle
# came from source that is in the tree too. The count of skipped files is
# always printed: a cap nobody is told about reads as coverage.
MAX_BYTES = 1024 * 1024

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

# A vendor's own SDK does not use the catalogue's spelling. Anthropic ships
# `claude-haiku-4-5-20251001`, the catalogue lists `anthropic/claude-haiku-4.5`;
# Bedrock ships `anthropic.claude-3-5-sonnet-20241022-v2:0`. Measured against
# the live catalogue on 2026-08-02, these rules fold 337 ids into 332 forms -
# only three collide, and every collision is a rolling alias sitting next to
# its own dated snapshots. So the rule is allowed to run ONLY as a last resort
# and ONLY where it lands on exactly one model.
_VENDOR_PREFIX = re.compile(r"^[a-z0-9]+\.")          # bedrock "anthropic."
_BEDROCK_REV = re.compile(r"-v\d+(?::\d+)?$")          # bedrock "-v2:0"
_DATE_PLAIN = re.compile(r"[-@]?20\d{6}$")             # "-20251001"
_DATE_DASHED = re.compile(r"-20\d{2}-\d{2}-\d{2}$")    # "-2024-05-13"


def normalize(name: str) -> str:
    s = name.lower().split("/")[-1]
    s = _VENDOR_PREFIX.sub("", s)
    s = _BEDROCK_REV.sub("", s)
    s = _DATE_DASHED.sub("", s)
    s = _DATE_PLAIN.sub("", s)
    return s.replace(".", "-")

SHUTDOWN_SOON_DAYS = 30

# A string that appears in this file and nowhere a user would write it, used
# to recognise any copy of this script during a scan.
SELF_MARK = "neosignal-check/1.0"


def money(v):
    if v is None:
        return "?"
    return ("$%.2f" % v) if v >= 0.10 else ("$%.3f" % v)


def _per_million(price):
    """Catalogue prices are per-token strings. Everything shown is per million.

    Returns None rather than 0.0 on anything unparseable, because a missing
    price rendered as free is worse than a missing price rendered as unknown.
    """
    try:
        return float(price) * 1_000_000
    except (TypeError, ValueError):
        return None


def fetch(url: str):
    # Ask for compression. urllib sends no Accept-Encoding of its own and does
    # not decompress, so every run was pulling the catalogue in full: 178KB
    # against 14KB on the wire, measured 2026-08-02. That is twelve times the
    # data for the same answer, on every machine, every run - and if this ever
    # lands on a front page it is the difference between a gigabyte of egress
    # and eighty megabytes. gzip is in the standard library, so the promise of
    # no dependencies survives.
    req = urllib.request.Request(url, headers={
        "User-Agent": "neosignal-check/1.0", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        # Asking is not receiving. A proxy or a future host may answer in the
        # clear, so the response header decides, never the request.
        if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
            raw = gzip.decompress(raw)
        return json.loads(raw.decode("utf-8"))


def walk(root: str):
    if os.path.isfile(root):
        yield root
        return
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS]
        for name in files:
            low = name.lower()
            if (os.path.splitext(low)[1] in READ_EXT
                    or low in READ_NAMES
                    or low.startswith(ENV_PREFIX)
                    or low.split(".")[0] in READ_NAMES):   # Dockerfile.prod
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


def norm_index(known: set) -> dict:
    """Normalised spelling -> the one model it can only mean.

    A form produced by two or more catalogue ids is dropped entirely. Every
    such collision measured so far is a rolling alias beside its own dated
    snapshots - `openai/gpt-4o` with `gpt-4o-2024-05-13` and `-2024-08-06` -
    where picking one would be picking which snapshot the reader meant. The
    same rule the bare-name index already follows: unambiguous or silent.
    """
    seen = {}
    for mid in known:
        seen.setdefault(normalize(mid), []).append(mid)
    return {k: v[0] for k, v in seen.items() if len(v) == 1}


def scan(root: str, known: set, bare: dict, norms: dict = None) -> dict:
    """Model ids you actually reference -> the files that reference them.

    Skips its own file. The intended way to run this is to curl it into the
    directory you want checked, and its documentation names real model ids as
    examples - so without this it reports three models from its own comments
    and the user has to work out which findings are about their code.
    """
    self_path = os.path.abspath(__file__)
    found = {}
    skipped = []
    for path in walk(root):
        if os.path.abspath(path) == self_path:
            continue
        try:
            if os.path.getsize(path) > MAX_BYTES:
                skipped.append(path)
                continue
        except OSError:
            continue
        try:
            # Bytes, then an explicit decode. A repository holds files in
            # whatever encoding their author used, so a strict read would stop
            # the scan at the first one - but "ignore" DELETES the undecodable
            # byte and closes the gap, gluing the text on either side into a
            # model id nobody wrote. A scanner that invents a finding is worse
            # than one that skips a file. Decoding with "replace" breaks the
            # token instead, and model ids are ASCII, so nothing real is lost.
            with open(path, "rb") as fh:
                text = fh.read().decode("utf-8", "replace")
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
        # Last resort, and only for tokens the two exact routes both refused.
        # Running it earlier would COST matches: `gpt-4o` resolves today by its
        # own name, and normalising it collides with two dated snapshots of
        # itself, so a normalise-first order would turn a working answer into
        # an ambiguous one.
        if norms:
            for t in CANDIDATE.findall(text) + BARE.findall(text):
                if len(t) < BARE_MIN_LEN or t in known:
                    continue
                mid = norms.get(normalize(t))
                if mid and mid not in hits:
                    hits.add(mid)
        for token in hits:
            found.setdefault(token, set()).add(rel)
    scan.skipped = skipped
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
        # An id can be missing from the catalogue for three different reasons,
        # and only one of them is a removal we actually watched happen. This
        # branch used to answer all three with the removal sentence, which
        # asserted a silent retirement for models we had never seen at all -
        # including a plain typo - and contradicted our own published record,
        # where a delisted addressing variant is deliberately NOT counted as a
        # retirement because every base model stayed listed.
        base = mid.split(":")[0] if ":" in mid else None
        if gone:
            when = gone[0].get("date")
            line = ("GONE from the catalogue%s, with no date in it beforehand"
                    % (" on " + when if when else ""))
        elif base and base in models:
            # The most actionable case the tool has: this call is broken right
            # now, the fix is one suffix away, and both halves are checkable
            # against the catalogue in front of us.
            return ("gone", "the ':%s' variant is no longer listed - the base model is"
                            % mid.split(":", 1)[1],
                    {"model": base, "kind": "same_model_base",
                     "price_per_million_output":
                         _per_million((models[base] or {}).get("pricing", {}).get("completion")),
                     "gone_price_per_million_output": None})
        else:
            # Say the true thing. We cannot tell a removal that predates our
            # tracking from a misspelling, and pretending otherwise is the one
            # failure that would make every other line here worth less.
            line = ("not in the catalogue, and we have no record of it leaving - "
                    "check the id, or it predates our tracking")
        # Where to go, when the data supports naming one. It often does not,
        # and the absence of a suggestion is itself information: nothing in
        # that vendor's remaining line-up is a defensible match. Better than
        # inventing one - the rule behind this was wrong four times before it
        # learned to stay quiet.
        move = next((r.get("replacement") for r in gone if r.get("replacement")), None)
        return ("gone", line, move)

    # A vendor's own retirement date, where the catalogue has none. This is
    # what the catalogue could not tell you: measured 2026-08-03, Anthropic
    # publishes 2026-08-05 for claude-opus-4.1 and the catalogue carries no
    # date for it or any of its sixteen siblings, so this returned "ok" for a
    # model with two days left. Checked before the catalogue's own field
    # because the vendor is the authority on its own schedule.
    vend = [r for r in rows if r.get("type") == "VENDOR_DEPRECATION"
            and r.get("expires_on")]
    if vend:
        v = min(vend, key=lambda r: r["expires_on"])
        when = v["expires_on"][:10]
        left = (dt.date(*map(int, when.split("-"))) - dt.date.today()).days
        move = v.get("replacement")
        # Say so when the claim is old. The collector keeps serving its last
        # good copy when a vendor page breaks, which is correct - the date does
        # not become false because our copy aged - but a month-old reading
        # presented exactly like this morning's is the kind of quiet staleness
        # this tool exists to catch elsewhere.
        read_on = (v.get("checked") or "")[:10]
        stale = ""
        if read_on:
            try:
                age = (dt.date.today() - dt.date(*map(int, read_on.split("-")))).days
                if age > 7:
                    stale = " (vendor page last read %d days ago)" % age
            except ValueError:
                pass
        if left < 0:
            # Not "gone" - the catalogue still lists it, and it may still
            # answer through an aggregator. Not "ok" either. Saying which of
            # the two sources disagrees is the whole value here.
            return ("soon", "its vendor retired this on %s - the catalogue still lists it%s"
                    % (when, stale), move)
        if left <= SHUTDOWN_SOON_DAYS:
            return ("soon", "vendor retires this %s - %d day%s left, not in the catalogue%s"
                    % (when, left, "" if left == 1 else "s", stale), move)
        return ("moved", "vendor retires this %s%s" % (when, stale), move)

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
    used = scan(args.path, known, bare_index(known), norm_index(known))

    results = []
    for mid in sorted(used):
        level, why, move = verdict(mid, models, changes)
        row = {"model": mid, "level": level, "detail": why, "files": used[mid]}
        if move:
            row["replacement"] = move
        results.append(row)

    # Worst first, BEFORE the json branch so both modes answer in the same
    # order. Pointed at a real repository the text output listed 370 models
    # alphabetically with the 48 that needed attention scattered through them,
    # and sorting only there left json consumers with the arbitrary order.
    rank = {"gone": 0, "soon": 1, "moved": 2, "ok": 3}
    results.sort(key=lambda r: (rank[r["level"]], r["model"]))

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
        # Always say what was not read. A cap nobody is told about reads as
        # coverage, which is the failure this tool exists to avoid.
        n_skip = len(getattr(scan, "skipped", []))
        note = ("  (%d file%s over 1 MB not read)"
                % (n_skip, "" if n_skip == 1 else "s")) if n_skip else ""
        print("%d model%s referenced in %s%s\n"
              % (len(results), "" if len(results) == 1 else "s", args.path, note))

    # And once the fine ones outnumber what a person will read, they become a
    # count. The list exists to show what is wrong; a screen of "ok" pushes it
    # off the top.
    quiet_ok = [r for r in results if r["level"] == "ok"]
    fold = len(quiet_ok) > 10 and not args.json

    for r in results:
        if args.quiet and r["level"] not in ("gone", "soon"):
            continue
        if fold and r["level"] == "ok":
            continue
        mark = {"gone": "GONE ", "soon": "SOON ", "moved": "moved", "ok": "ok   "}[r["level"]]
        print("  %s  %-46s %s" % (mark, r["model"], r["detail"]))
        move = r.get("replacement")
        if move and move.get("kind") == "vendor_stated":
            # Stated by the vendor on its own deprecation page, not inferred
            # from id similarity. Labelled as such because the difference is
            # the whole reason to trust it.
            print("         the vendor names %s as the replacement" % move["model"])
        elif move and move.get("kind") == "same_model_base":
            # Not a migration. The same model answers at a shorter id, so the
            # "against the $X it cost" comparison would be comparing a price
            # with itself.
            print("         drop the suffix: %s at %s per million output"
                  % (move["model"], money(move.get("price_per_million_output"))))
        elif move:
            print("         nearest still listed: %s at %s per million output, "
                  "against the %s it cost"
                  % (move["model"], money(move.get("price_per_million_output")),
                     money(move.get("gone_price_per_million_output"))))
        # Anything but `ok` names where it is. This used to cover gone and soon
        # only, which was fine while `moved` meant a price change - but `moved`
        # now also carries a vendor retirement further out than 30 days, and
        # telling someone their model retires in October without saying which
        # file to edit leaves them to grep for it.
        if r["level"] != "ok":
            for f in r["files"][:4]:
                print("         %s" % f)

    if bad:
        print("\n%d need%s attention. Full history: %s/gone.html"
              % (len(bad), "s" if len(bad) == 1 else "", SITE))
        return 1
    if not args.quiet:
        # NOT "nothing you call is going away". That is a completeness claim,
        # and this cannot make one. Measured 2026-08-03: Anthropic publishes a
        # retirement date for claude-opus-4.1 of 2026-08-05 on its own docs,
        # the catalogue read here carries no date for it, and this printed an
        # all-clear and exited 0 for a model with two days left. A checker that
        # oversells its own coverage is the failure this project keeps saying
        # is worse than no checker.
        print("\nNo change recorded for these in the catalogue.")
        print("That is what this can see - a vendor's own deprecation page may")
        print("carry a date the catalogue does not. %s/gone.html" % SITE)
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
A deprecation calendar can only list what somebody announced. aimodelwatch.dev,
read 2026-08-03, describes its data as "Sourced from official docs, refreshed
daily" - a good service, and sound for everything a vendor writes down. The gap
is what nobody wrote down: a model that is simply gone one morning, with nothing
published anywhere, was never on a calendar because there was no date to put
there.

This checks against a catalogue that is diffed every day. Of the removals it has
recorded, two were announced by their vendor beforehand and three were not; none
of them carried an end-of-life date in the CATALOGUE, which is the field
anything reading only the catalogue has to rely on.

(The quote above was wrong here until 2026-08-03. It read "sourced from official
deprecation pages" - narrower than what they actually say, and the narrower
version happened to be the one that made this paragraph's argument work.)

AND THE OTHER DIRECTION
A vendor can publish a retirement date the catalogue never carries. Measured
2026-08-03: Anthropic publishes 2026-08-05 for claude-opus-4.1 and the
catalogue holds no date for it or its sixteen siblings, so this reported "no
change recorded" for a model with two days left. Vendor deprecation pages are
read directly now and merged into the same change record, which is why a
warning can say the vendor retires something the catalogue still lists.

NO KEY, NO SIGNUP, NO ACCOUNT. It reads two public JSON files.

IT READS THE SPELLINGS PEOPLE ACTUALLY WRITE
`openai/gpt-5.2-chat` is the OpenRouter form; a vendor SDK takes the bare
`gpt-5.2-chat`; a vendor's own dated pin looks like
`claude-haiku-4-5-20251001`; and a router puts its route in front -
`azure/gpt-4o`, `bedrock/anthropic.claude-3-haiku-20240307-v1:0`,
`vertex_ai/gemini-2.5-pro`. All of them resolve, each only where it lands on
exactly one model, so a suffix two vendors share is skipped rather than
guessed at.

HuggingFace repository ids resolve too - `Qwen/Qwen3-30B-A3B-Instruct-2507`,
`deepseek-ai/DeepSeek-R1` - and so does the case you wrote it in. Until
2026-08-04 it did not: `GPT-4` resolved and `GPT-4o` did not, because the
bare-name index matched case exactly while the normalising one folded it, and
which index a model lives in is invisible from outside. Measured across four
repository trees, that was 220 occurrences of `GPT-4o` and 81 of
`GPT-4o-mini`, every one of them silently unreported.

The route prefixes were never designed for - measured 2026-08-04, they already
worked, because the bare-name pass finds the model inside them. They are named
here and pinned by tests now, because a behaviour nobody wrote down is a
behaviour somebody removes.

AND THE SPELLING SAYS WHICH DEADLINE IS YOURS
A retirement date belongs to a model ON A PLATFORM. Anthropic retired
claude-3-haiku on 2026-04-20; AWS Bedrock serves it until 2026-09-10. If your
code says `anthropic.claude-3-haiku-20240307-v1:0` you are on Bedrock and
September is your date; if it says `claude-3-haiku-20240307` you lost it in
April. Both spellings resolve to one catalogue id, so until 2026-08-03 this
gave every caller the vendor's date - wrong by 143 days for the Bedrock one,
and wrong in the direction where nothing breaks when the tool said it would.
A tree that spells it both ways gets the vendor date and no guess.

WHERE IT LOOKS
Source in most languages, plus the places a model id actually hides: Jupyter
notebooks, Dockerfiles, Makefiles, Terraform, Gradle, and config of every
shape. An earlier version filtered on extension alone and found NONE of those
four - and then printed "either a clean bill or the wrong directory", which
reads as a pass. A missed model is worse than no tool, because the tool was
trusted.

HOW IT AVOIDS CRYING WOLF
It does not guess what a model id looks like. Every candidate token is kept
only if it resolves to exactly one real id, so `utils/helpers`,
`read-timeout-30` and `on-click-handler` cannot survive. A bare name must also
contain a digit, a hyphen, and at least five characters. A false positive would
require a variable named exactly after a real model.

(This said six characters until 2026-08-03, when six was measured to exclude
`gpt-4` and `gpt-5` - the most common way anyone names a model - and a file
containing nothing else got a clean bill. The uniqueness requirement is what
does the work a length rule was credited with.)
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
import time
import urllib.error
import urllib.request

# A CI step that curls this file gets whatever is current, so a build that
# passed yesterday can fail today because the TOOL changed rather than the code.
# There was no version at all until 2026-08-04, and no way to say which one said
# what. Dated rather than semver: this ships continuously and a date is the
# honest description of "the copy from that day".
#
# Hand-set, unlike every other number here, because a version is a decision
# rather than a measurement - it should move when someone judges the behaviour
# changed, not because a vendor edited a page overnight.
# Same day, second build. The date alone stopped identifying the code the
# moment v2026.08.04 was tagged and this file changed underneath it - a CI job
# that reports a version has to be able to name ONE tool, which is the entire
# reason the field exists.
__version__ = "2026.08.05.2"

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
#   - at least 5 characters, so short ids cannot collide with a variable name
#   - must contain a digit, which every real model id does and most English
#     words do not
#
# The floor was 6, and 6 excluded `gpt-4` and `gpt-5`. Measured 2026-08-03: a
# file containing nothing but `model="gpt-4"` and `model="gpt-5"` - the most
# common way anyone writes either - reported "No model ids from the catalogue
# appear" and exited 0. That is the first thing a sceptical reader tries, and
# it is the answer least likely to make them try a second thing.
#
# Dropping to 5 admits exactly four ids and no others, because a token is only
# ever reported if it resolves to exactly one catalogue name: `gpt-4`, `gpt-5`,
# `phi-4`, `glm-5`. It cannot admit `o1`, `o3`, `auto`, `free`, `sonar` or
# `hy3` - the regex above requires at least one hyphen group, so those are
# unreachable by this path at any floor, and they are the ones a length rule
# was really guarding against. The floor was doing almost none of the work the
# comment claimed; the uniqueness requirement does it.
BARE = re.compile(r"[A-Za-z][A-Za-z0-9._]*(?:-[A-Za-z0-9._]+)+")
BARE_MIN_LEN = 5

# A vendor's own SDK does not use the catalogue's spelling. Anthropic ships
# `claude-haiku-4-5-20251001`, the catalogue lists `anthropic/claude-haiku-4.5`;
# Bedrock ships `anthropic.claude-3-5-sonnet-20241022-v2:0`. Measured against
# the live catalogue on 2026-08-02, these rules fold 337 ids into 332 forms -
# only three collide, and every collision is a rolling alias sitting next to
# its own dated snapshots. So the rule is allowed to run ONLY as a last resort
# and ONLY where it lands on exactly one model.
# A spelling says WHERE the caller is calling from, and that decides which
# deadline is theirs. `anthropic.claude-3-haiku-20240307-v1:0` is a Bedrock id
# and nothing else; `claude-3-haiku-20240307` is Anthropic's own SDK. Both
# resolve to the same catalogue entry, and the normalisation that makes that
# work is exactly the step that throws the platform away.
#
# It matters by months. Anthropic retired claude-3-haiku on 2026-04-20; AWS
# Bedrock serves it until 2026-09-10. Before this, a repository calling it
# through Bedrock was told its model died in April - true about the vendor,
# wrong about the reader's deadline by 143 days, and wrong in the direction
# that makes someone distrust the tool when nothing breaks in April.
PLATFORM_SPELLING = [
    ("AWS Bedrock", re.compile(r"^[a-z0-9]+\.[a-z0-9][a-z0-9.\-]*-v\d+(?::\d+)?$")),
]


def platform_of(token: str):
    """The platform a spelling belongs to, or None for a vendor-native id."""
    for name, rx in PLATFORM_SPELLING:
        if rx.match(token.lower()):
            return name
    return None


_VENDOR_PREFIX = re.compile(r"^[a-z0-9]+\.")          # bedrock "anthropic."
_BEDROCK_REV = re.compile(r"-v\d+(?::\d+)?$")          # bedrock "-v2:0"
_DATE_PLAIN = re.compile(r"[-@]?20\d{6}$")             # "-20251001"
_DATE_DASHED = re.compile(r"-20\d{2}-\d{2}-\d{2}$")    # "-2024-05-13"

# Bedrock writes Meta's family as `llama3-3-70b-instruct`; the catalogue writes
# `llama-3.3-70b-instruct`. Everything else about the two spellings already
# folds together - only the missing separator between the letters and the
# version digit keeps them apart, so a hyphen is inserted at that boundary on
# both sides. Applied last, after the dots have already become dashes, so
# `qwen3.5-35b-a3b` and `qwen3-5-35b-a3b` land on the same form too.
#
# Measured against the live catalogue before adding it: this creates ZERO new
# collisions. The three that exist are unchanged and are the same rolling
# aliases beside their own dated snapshots that norm_index already drops. A
# folding rule that quietly merged two different models would be worse than
# the miss it fixes, which is why the number was checked rather than assumed.
_LETTER_DIGIT = re.compile(r"(?<=[a-z])(?=\d)")        # "llama3" -> "llama-3"


def normalize(name: str) -> str:
    s = name.lower().split("/")[-1]
    # Strip a Bedrock vendor prefix only when a model name is left behind.
    # `^[a-z0-9]+\.` cannot tell `anthropic.claude-3-haiku` from `qwen3.5-27b`,
    # and it was reading the version dot as a vendor separator: 19 catalogue
    # ids, every Qwen with a dotted version, normalised to things like `5-27b`
    # and `5-vl-72b-instruct`. They were unreachable through this path
    # entirely - not misread, just gone. A real vendor prefix is always
    # followed by a name that starts with a letter, and a version never is, so
    # that is the test. Keeping the strip only when it produces something
    # name-shaped fixes all 19 and leaves every Bedrock spelling working.
    stripped = _VENDOR_PREFIX.sub("", s)
    if stripped and stripped[0].isalpha():
        s = stripped
    s = _BEDROCK_REV.sub("", s)
    s = _DATE_DASHED.sub("", s)
    s = _DATE_PLAIN.sub("", s)
    return _LETTER_DIGIT.sub("-", s.replace(".", "-"))

SHUTDOWN_SOON_DAYS = 30

# Beyond this, a catalogue expiry date is a placeholder meaning "no expiry"
# rather than a shutdown anyone planned. Ten years: the longest genuine notice
# period anywhere in this record is under two, so a decade is comfortably past
# every real plan and comfortably short of the 2098-12-31 the catalogue
# actually uses for 2 of its 5 dated models.
SENTINEL_EXPIRY_DAYS = 3650

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

    Keyed in LOWERCASE, and looked up that way. This index used to match case
    exactly while the normalising path did not, so `GPT-4` resolved and
    `GPT-4o` did not - and the difference was invisible, because it depends on
    which index a model happens to live in. `gpt-4o` collides with its own
    dated snapshots, so it is dropped from the normalising index and reachable
    only here; write it the way most of the world writes it and the tool said
    nothing at all. Measured 2026-08-04 across four repository trees: 220
    occurrences of `GPT-4o` and 81 of `GPT-4o-mini`, every one of them silent.

    A miss is the dangerous direction. A false positive argues with you; this
    prints a clean bill.
    """
    counts, first = {}, {}
    for mid in known:
        tail = mid.split("/", 1)[-1].lower()
        if len(tail) < BARE_MIN_LEN or not any(c.isdigit() for c in tail):
            continue
        counts[tail] = counts.get(tail, 0) + 1
        first.setdefault(tail, mid)
    # Uniqueness is counted on the LOWERED key, so two ids differing only by
    # case would be dropped as ambiguous rather than one silently winning.
    # No catalogue id needs that today - every one is already lowercase - so
    # this half is a guard against a future id, and no test can reach it. The
    # half that does the work is lowering the TOKEN at the lookup, and that is
    # pinned.
    return {t: first[t] for t, n in counts.items() if n == 1}


def norm_index(known: set) -> dict:
    """Normalised spelling -> the one model it can only mean.

    A form produced by two or more catalogue ids is dropped entirely. Every
    such collision measured so far is a rolling alias beside its own dated
    snapshots - `openai/gpt-4o` with `gpt-4o-2024-05-13` and `-2024-08-06` -
    where picking one would be picking which snapshot the reader meant. The
    same rule the bare-name index already follows: unambiguous or silent.

    The catalogue does sell models called `auto` and `free`, so entries here
    can be indistinguishable from an English word. That is not filtered at this
    layer - the index is keyed by the model, and the ambiguity belongs to the
    TOKEN being resolved. scan() guards it where the token is still visible.
    """
    seen = {}
    for mid in known:
        seen.setdefault(normalize(mid), []).append(mid)
    return {k: v[0] for k, v in seen.items() if len(v) == 1}


def scan(root: str, known: set, bare: dict, norms: dict = None,
         progress=None) -> dict:
    """Model ids you actually reference -> the files that reference them.

    Skips its own file. The intended way to run this is to curl it into the
    directory you want checked, and its documentation names real model ids as
    examples - so without this it reports three models from its own comments
    and the user has to work out which findings are about their code.
    """
    self_path = os.path.abspath(__file__)
    found = {}
    skipped = []
    plats = {}
    # Asked ONCE. This is loop-invariant - root does not change - and it used to
    # sit on the relpath line below, so it ran per file. Measured 2026-08-04:
    # 800 files spent 7.7 of 24.2 seconds re-answering the same question.
    root_is_dir = os.path.isdir(root)
    seen_files = 0
    for path in walk(root):
        if os.path.abspath(path) == self_path:
            continue
        seen_files += 1
        if progress is not None:
            progress(seen_files)
        try:
            # Size from the OPEN HANDLE, never a second look at the path. Same
            # measurement: a path-based stat cost 9.7ms per file against 5.1ms
            # for the open itself, because real-time antivirus inspects every
            # path this process resolves and charges us again for the second
            # one. fstat asks the handle already paid for, so the large-file
            # guard below became free - and it still refuses to READ the file
            # until the size has cleared, which is the point of the guard.
            fh = open(path, "rb")
        except OSError:
            continue
        try:
            if os.fstat(fh.fileno()).st_size > MAX_BYTES:
                skipped.append(path)
                continue
            # Bytes, then an explicit decode. A repository holds files in
            # whatever encoding their author used, so a strict read would stop
            # the scan at the first one - but "ignore" DELETES the undecodable
            # byte and closes the gap, gluing the text on either side into a
            # model id nobody wrote. A scanner that invents a finding is worse
            # than one that skips a file. Decoding with "replace" breaks the
            # token instead, and model ids are ASCII, so nothing real is lost.
            text = fh.read().decode("utf-8", "replace")
        except (OSError, ValueError):
            continue
        finally:
            fh.close()
        # Skip ANY copy of this script, not only the one being executed. The
        # documented usage curls it into the directory under test, so a second
        # copy sitting there is normal - and its own documentation names real
        # model ids as examples, which would be reported as the user's.
        if SELF_MARK in text:
            continue
        rel = os.path.relpath(path, root) if root_is_dir else path
        # (token, model) pairs, not just models: the SPELLING is what says
        # which platform the caller is on, and it is discarded a few lines
        # later by the very normalisation that makes the match work.
        pairs = [(t, t) for t in CANDIDATE.findall(text) if t in known]
        hits = {t for t, _ in pairs}
        # Only look for bare names where the prefixed form did not already
        # match on this line's id, so a file using the full form is not
        # reported twice under two spellings.
        for t in BARE.findall(text):
            mid = bare.get(t.lower())
            if mid and mid not in hits:
                hits.add(mid)
                pairs.append((t, mid))
        # Last resort, and only for tokens the two exact routes both refused.
        # Running it earlier would COST matches: `gpt-4o` resolves today by its
        # own name, and normalising it collides with two dated snapshots of
        # itself, so a normalise-first order would turn a working answer into
        # an ambiguous one.
        if norms:
            for t in CANDIDATE.findall(text) + BARE.findall(text):
                if len(t) < BARE_MIN_LEN or t in known:
                    continue
                n = normalize(t)
                # normalize() keeps only the last path segment, so `billing/free`
                # and `apis/edgecontainer/v1/auto` arrive here as `free` and
                # `auto` - and the catalogue really does sell `openrouter/free`
                # and `openrouter/auto`. Measured 2026-08-04 over a Google Cloud
                # SDK checkout: both were reported across four files, from
                # ordinary path strings, which is precisely the crying wolf the
                # README promises does not happen.
                #
                # The guard is ONLY for tokens that had a path prefix dropped.
                # A digit test on every token would have been wrong: Bedrock
                # writes `amazon.nova-pro-v1:0`, which folds to `nova-pro` with
                # no digit left, and that spelling is a headline feature. It has
                # no slash, so it never reaches this line. What is given up is
                # narrower - a route-prefixed spelling of a digit-free name,
                # `azure/mistral-large` - and unlike `something/free` that has
                # to be deliberately written to occur at all.
                if "/" in t and not any(c.isdigit() for c in n):
                    continue
                # The length rule belongs to the part that DOES the matching,
                # not to the raw token. It was checked against `t` above, and
                # `t` is whatever the file happened to hold - so
                # `sha512-KhYd2Hjt/O1`, an npm integrity hash, passed at 19
                # characters and then resolved on its last two. Measured
                # 2026-08-04: that exact string is in a package-lock.json in
                # this workspace and resolved to `openai/o1`.
                #
                # Not a curiosity. Base64 has no hyphen, so a lockfile can only
                # produce SHORT names this way - and a slash followed by two
                # base64 characters comes up about once in four thousand
                # positions, against the hundreds of thousands of positions in
                # a large lockfile. Every JavaScript repository carries one.
                #
                # Five models normalise below this length: auto and free, which
                # the digit rule above already refuses, plus o1, o3 and hy3.
                # Those three keep their exact spelling and lose only the folded
                # route, so `azure/o1` goes unmatched. That is the price, and it
                # is smaller than a fabricated finding in every lockfile.
                if len(n) < BARE_MIN_LEN:
                    continue
                mid = norms.get(n)
                if mid and mid not in hits:
                    hits.add(mid)
                    pairs.append((t, mid))
        # Record the platform every spelling belongs to, INCLUDING None for a
        # vendor-native one. Tracking only the platforms was a real defect: a
        # tree calling a model both ways produced the set {"AWS Bedrock"}, so
        # the "exactly one platform" guard passed and every file was told the
        # Bedrock date - including the one calling Anthropic directly, whose
        # deadline was five months earlier. None has to be in the set for the
        # guard to see the disagreement.
        for token, mid in pairs:
            plats.setdefault(mid, set()).add(platform_of(token))
        for token in hits:
            found.setdefault(token, set()).add(rel)
    scan.skipped = skipped
    # Only models spelled ONE way, and that way a platform. Anything else -
    # mixed spellings, or a vendor-native id - resolves to no platform, and
    # verdict() falls back to the vendor date rather than guessing.
    scan.platforms = {k: sorted(v) for k, v in plats.items()
                      if len(v) == 1 and None not in v}
    return {k: sorted(v) for k, v in found.items()}


def _days_until(iso: str) -> int:
    """Days from today to an ISO date; a huge number if it cannot be read,
    so an unparseable date is treated as far off rather than as an emergency."""
    try:
        return (dt.date(*map(int, iso[:10].split("-")))
                - dt.datetime.now(dt.timezone.utc).date()).days
    except (ValueError, TypeError):
        return 10 ** 6


def _today_iso() -> str:
    """Today in UTC, as the dates in the change record are written."""
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def verdict(mid: str, models: dict, changes: dict,
            on: list = None, plat: dict = None, out: dict = None,
            pulled: dict = None, delisted: dict = None) -> tuple:
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
        elif (delisted or {}).get(mid):
            # The vendor's own page still carries this one, long after the
            # catalogue stopped listing it. That is a STRONGER statement than
            # anything the catalogue diff can make - it is the vendor saying it
            # retired the model, on a date, rather than us observing an entry
            # disappear - and until 2026-08-04 it was collected every day and
            # thrown away, because the merge keyed on catalogue ids and dropped
            # whatever the catalogue no longer listed.
            #
            # This is the case old code actually hits. The first snapshot here
            # is dated 2026-07-29, so a diff can never reach claude-3-opus or
            # gpt-4-32k; the vendor page reaches back years, and a codebase
            # written last year is full of them.
            rec = delisted[mid]
            # Name the vendor's OWN spelling when it differs from the id shown.
            # The key has to be the normalised form or nothing would match it,
            # but that form is synthetic - `google/gemini-2-0-flash` is a
            # spelling nobody wrote and reads like the tool inventing a model.
            # The vendor id is the checkable thing: it is what is printed on
            # the page the date came from.
            vid = rec.get("vendor_id")
            said = (" - the vendor's page calls it %s" % vid) if vid and vid != mid.split("/", 1)[-1] else ""
            # Tense follows the DATE, not the branch. 38 of these carry a
            # retirement date in the future, and saying "its vendor retired it
            # on 2026-08-05" the day before is simply false - caught by running
            # this over a third-party repository and reading a line that
            # contradicted what this same tool said about the same model that
            # morning.
            when = rec.get("retires_on", "")
            # LEVEL follows the date too, not just the wording. Fixing the tense
            # and leaving the severity alone shipped `gpt-4o-mini-transcribe`
            # as GONE with a 2027 date, and `gemini-embedding-001` as GONE
            # while its vendor serves it until 2028 - 23 of 173 records more
            # than a month out, all at the most severe level this tool has.
            # GONE means you cannot call this any more. A model with a year to
            # run is information, and reporting it as an emergency is the
            # crying wolf the README promises does not happen.
            if when and when > _today_iso():
                line = ("its vendor retires it on %s and it is not in the "
                        "catalogue%s" % (when, said))
                lvl = "soon" if _days_until(when) <= SHUTDOWN_SOON_DAYS else "moved"
                if out is not None:
                    out["source"] = rec.get("source")
                    out["vendor_id"] = rec.get("vendor_id")
                return (lvl, line, None)
            line = ("its vendor retired it on %s, and it is no longer in "
                    "the catalogue%s" % (when or "?", said))
            if out is not None:
                out["source"] = rec.get("source")
                out["vendor_id"] = rec.get("vendor_id")
            return ("gone", line, None)
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
    # If the caller's own spelling says which platform they are on, that
    # platform's date is theirs and the vendor's is not. Only when exactly one
    # platform was seen for this model: a tree calling it both ways has two
    # real deadlines and picking either would be inventing an answer.
    if on and len(on) == 1 and plat:
        for row in plat.get(mid) or []:
            if row.get("platform") != on[0] or not row.get("end_of_life"):
                continue
            when = row["end_of_life"][:10]
            left = (dt.date(*map(int, when.split("-"))) - dt.date.today()).days
            vend_when = min((r["expires_on"][:10] for r in rows
                             if r.get("type") == "VENDOR_DEPRECATION"
                             and r.get("expires_on")), default=None)
            # Say the vendor's date too where it differs, or the reader sees a
            # number here and a different one on the model page and has no way
            # to tell which of us is wrong. Neither is.
            also = ""
            if vend_when and vend_when != when:
                also = (" (its vendor's own date is %s; you are reading the %s "
                        "one because that is how your code calls it)"
                        % (vend_when, on[0]))
            # Structured, not only in the prose. This file already argues the
            # point about `replacement`: putting data a consumer needs inside
            # an English sentence makes them parse it back out. The platform,
            # its date and the vendor's differing one are exactly that kind of
            # data, and a CI job keying on "whose deadline is this" should not
            # have to read the headline.
            # Filled into a dict the caller owns rather than returned. The
            # first attempt returned a fourth element only on this branch, so
            # verdict's arity depended on which path it took - and the tests
            # that unpack three broke the moment a platform answered. A
            # function whose shape varies by branch is a trap whoever writes
            # the next caller will also fall into.
            if out is not None:
                out["platform"] = on[0]
                out["platform_end_of_life"] = when
                out["source"] = row.get("source") or ""
                if vend_when and vend_when != when:
                    out["vendor_end_of_life"] = vend_when
            if left < 0:
                return ("gone", "%s stopped serving this on %s%s"
                        % (on[0], when, also), None)
            if left <= SHUTDOWN_SOON_DAYS:
                return ("soon", "%s stops serving this %s - %d day%s left%s"
                        % (on[0], when, left, "" if left == 1 else "s", also),
                        None)
            return ("moved", "%s stops serving this %s%s" % (on[0], when, also),
                    None)

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
            # This branch is only reached for a model the catalogue DOES list -
            # `models[mid]` is read a few lines below - and its sibling three
            # lines up says exactly that. It nevertheless shipped saying "not
            # in the catalogue", so the tool told a reader that a model they
            # can call today is absent from the catalogue, in the same output
            # where another line said the opposite about the same situation.
            #
            # Found by running this over a third-party repository, where the
            # line rendered as `claude-opus-4.1 - 0 days left, not in the
            # catalogue` for a model that is in the catalogue right now and
            # retires today. That is the worst possible day for the sentence
            # to be wrong.
            #
            # The author's intent was "the DATE is not the catalogue's" - the
            # warning comes from the vendor page, which is this tool's whole
            # differentiating claim - and a test pinned that intent. But the
            # subject of the sentence is the model, so a reader parses it as
            # the model being absent. Both facts are worth keeping, so both
            # are said: the catalogue lists it, and the catalogue has no
            # end-of-life date for it.
            return ("soon", "vendor retires this %s - %d day%s left; the "
                    "catalogue lists it with no end-of-life date%s"
                    % (when, left, "" if left == 1 else "s", stale), move)
        return ("moved", "vendor retires this %s%s" % (when, stale), move)

    eol = (models[mid] or {}).get("expiration_date")
    if eol:
        # Counted from the date, not read from the event. `days_left` is
        # written when an event is recorded and never updated, so it is exactly
        # as old as the day something last changed for that model. Measured
        # 2026-08-04 against the live API: gpt-5.2-chat and gpt-5.3-chat both
        # stored 8 for a date 6 days away, and z-ai/glm-4.5 and glm-4.5v stored
        # 151 and 154 for the SAME date - the two are not even consistent with
        # each other, which is what a frozen number looks like once a few days
        # of events have gone by.
        #
        # The countdown is the one number a user acts on. A deadline tool that
        # is two days optimistic about a deadline is worse than no tool.
        days = None
        try:
            days = (dt.date(*map(int, eol[:10].split("-"))) - dt.date.today()).days
        except (ValueError, TypeError):
            left = [r.get("days_left") for r in rows
                    if r.get("type") == "DEPRECATION_DEADLINE"
                    and r.get("days_left") is not None]
            days = min(left) if left else None
        if days is not None and days < 0:
            return ("soon", "the catalogue says this shut down %s - it is still "
                            "listed" % eol, None)
        if days is not None and days <= SHUTDOWN_SOON_DAYS:
            return ("soon", "shuts down %s - %d day%s left"
                    % (eol, days, "" if days == 1 else "s"), None)
        # A date decades out is a placeholder for "no expiry", not a plan.
        # Measured against the live catalogue 2026-08-05: 5 of 338 models carry
        # an expiration_date at all, and 2 of those 5 say 2098-12-31 - seventy-
        # two years out, which is not a product decision anybody made. The tool
        # reported them as "shuts down 2098-12-31", which is a finding about a
        # non-event, and a tool that reports non-events teaches the reader to
        # skim the ones that matter.
        #
        # Ten years rather than a match on 2098, because the sentinel value is
        # the catalogue's choice and it can change; what makes it a sentinel is
        # being further out than any real deprecation plan. Nothing genuine has
        # ever been announced a decade ahead - the longest real notice in this
        # whole record is under two years.
        if days is not None and days > SENTINEL_EXPIRY_DAYS:
            return ("ok", "no change recorded", None)
        return ("moved", "shuts down %s" % eol, None)

    # A date the vendor published and has since taken back. Checked after the
    # live dates and before "no change recorded", because it is neither: there
    # is no deadline any more, and something did change.
    #
    # Measured 2026-08-04: Google carried 2026-10-16 for gemini-2.5-pro and its
    # page now carries nothing. Anyone who ran this last week was told to
    # migrate by October. Today they were told "no change recorded" with no
    # explanation - the same quiet change this tool exists to catch, in the
    # tool itself. Someone planning around October should hear that the plan
    # rests on something the vendor no longer says.
    took_back = (pulled or {}).get(mid)
    if took_back and took_back.get("had"):
        if out is not None:
            out["withdrawn_date"] = took_back["had"]
            out["withdrawn_noticed"] = took_back.get("noticed") or ""
        return ("moved", "its vendor published %s and has since withdrawn it - "
                         "there is no published date now"
                % took_back["had"], None)

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
    ap.add_argument("--version", action="version",
                    version="neosignal-check %s" % __version__)
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
        payload = fetch(CHANGES_URL)
        changes = payload.get("changes") or {}
        # A date the vendor published and then took back. Its own key, not a
        # row in `changes`, because it is not something the vendor now says.
        pulled = {r.get("model"): r for r in
                  (payload.get("vendor_date_withdrawn") or []) if r.get("model")}
        # Platform end-of-life, published under its own key precisely so a
        # reader has to opt into it rather than have it merged in.
        plat = payload.get("platform_lifecycles") or {}
        # Vendor-published retirements for models the catalogue no longer
        # lists. Its own key rather than merged into `changes`, because every
        # published figure about models "still listed after retirement" is
        # scoped to the catalogue and would move if these joined it.
        delisted = payload.get("retired_and_delisted") or {}
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

    known = set(models) | set(changes) | set(delisted)

    # A line while the walk is quiet. Measured 2026-08-04 on a 1,334-file tree:
    # 23 minutes with NOTHING on screen until the very end, because every file
    # is a real disk read that this host's antivirus inspects. A tool that looks
    # hung gets killed, and the reader concludes it is broken rather than slow -
    # so the silence was the worse defect, not the speed.
    #
    # stderr, never stdout: --json has to stay parseable and a pipe has to stay
    # clean. Only when stderr is a terminal, so redirected logs and CI do not
    # collect thousands of carriage returns. --quiet means quiet.
    tick = None
    if not args.quiet and sys.stderr.isatty():
        last = [0.0]

        def tick(n, _last=last):
            now = time.time()
            if now - _last[0] < 0.4:      # throttled by TIME, not by file count:
                return                    # a tree of huge files is just as quiet
            _last[0] = now
            sys.stderr.write("\r  reading %d files..." % n)
            sys.stderr.flush()

    used = scan(args.path, known, bare_index(known), norm_index(known),
                progress=tick)
    if tick is not None:
        sys.stderr.write("\r" + " " * 32 + "\r")   # erase it before real output
        sys.stderr.flush()

    results = []
    for mid in sorted(used):
        # verdict returns three items, or four when a platform answered. Not a
        # dict, because every other caller and every test unpacks the triple.
        extra = {}
        level, why, move = verdict(mid, models, changes,
                                   getattr(scan, "platforms", {}).get(mid),
                                   plat, extra, pulled, delisted)
        row = {"model": mid, "level": level, "detail": why, "files": used[mid]}
        if move:
            row["replacement"] = move
        row.update(extra)
        results.append(row)

    # Worst first, BEFORE the json branch so both modes answer in the same
    # order. Pointed at a real repository the text output listed 370 models
    # alphabetically with the 48 that needed attention scattered through them,
    # and sorting only there left json consumers with the arbitrary order.
    rank = {"gone": 0, "soon": 1, "moved": 2, "ok": 3}
    results.sort(key=lambda r: (rank[r["level"]], r["model"]))

    bad = [r for r in results if r["level"] in ("gone", "soon")]

    if args.json:
        # The version travels with the payload. A CI job that logs this should
        # be able to say which copy of the tool produced a verdict, because the
        # documented install is a curl that gets whatever is current.
        print(json.dumps({"tool_version": __version__,
                          "scanned": args.path, "models_referenced": len(results),
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
        dated = [r for r in results if r["level"] == "moved"]
        if dated:
            # A `moved` row already printed a real retirement date. Following
            # it with "no change recorded" reads as the tool contradicting the
            # line above it, and the reader has to decide which half to trust.
            # Both are true - the date is real and none of them is inside the
            # next 30 days - so say that instead.
            # "has a date against it" was written when `moved` only ever meant a
            # future deadline. A withdrawn date is also `moved` and is the exact
            # opposite - the date is gone - so the summary contradicted the line
            # printed directly above it.
            print("\n%d of these ha%s something recorded against %s, nothing "
                  "inside %d days."
                  % (len(dated), "s" if len(dated) == 1 else "ve",
                     "it" if len(dated) == 1 else "them", SHUTDOWN_SOON_DAYS))
            print("Nothing here is urgent today. %s/gone.html" % SITE)
            return 0
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

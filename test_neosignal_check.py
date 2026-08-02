#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for neosignal_check. Standard library only, no network.

    python test_neosignal_check.py

Every case here is a bug this tool actually shipped, or nearly shipped, during
its first day. They are written as the behaviour that was wrong at the time,
because a test that only asserts what the code happens to do now protects
nothing.

The catalogue is inlined rather than fetched. A test that needs the network is
a test that fails on a plane, and none of the logic worth protecting depends on
where the data came from.
"""

from __future__ import annotations

import datetime as dt
import gzip
import io
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import neosignal_check as N  # noqa: E402

# A miniature catalogue with the shapes that matter: a live model, a live model
# with a shutdown date, a sibling pair sharing a suffix, and two ids that a
# careless matcher confuses with each other.
MODELS = {
    "anthropic/claude-haiku-4.5": {"context_length": 200000,
                                   "pricing": {"completion": "0.000004"}},
    "openai/gpt-5.2-chat": {"context_length": 128000, "expiration_date": "2026-08-10",
                            "pricing": {"completion": "0.000014"}},
    "openai/gpt-5.1-codex": {"context_length": 400000,
                             "pricing": {"completion": "0.00001"}},
    "openai/gpt-5.1": {"context_length": 400000, "pricing": {"completion": "0.00001"}},
    "openai/gpt-5-image": {"context_length": 400000, "pricing": {"completion": "0.00001"}},
    "acme/shared-suffix-9": {"context_length": 8000, "pricing": {"completion": "0.000001"}},
    "other/shared-suffix-9": {"context_length": 8000, "pricing": {"completion": "0.000001"}},
}

CHANGES = {
    "openai/gpt-5-codex": [{
        "type": "MODEL_REMOVED", "date": "2026-07-30",
        "replacement": {"model": "openai/gpt-5.1-codex",
                        "price_per_million_output": 10.0,
                        "gone_price_per_million_output": 10.0},
    }],
    "mistralai/devstral-2512": [{"type": "MODEL_REMOVED", "date": "2026-08-01"}],
    "openai/gpt-5.2-chat": [{"type": "DEPRECATION_DEADLINE", "days_left": 9,
                             "expires_on": "2026-08-10"}],
    "anthropic/claude-haiku-4.5": [],
    # An addressing variant that left the catalogue while its base model stayed.
    # Deliberately carries NO removal record, because the pipeline classifies a
    # variant delisting as a catalogue change rather than a retirement.
    "openai/gpt-5.1:batch": [{"type": "PRICING_CHANGE", "date": "2026-07-20"}],
    # Known to us, absent from the catalogue, never observed leaving.
    "ghost/never-seen-go": [{"type": "PRICING_CHANGE", "date": "2026-07-11"}],
}

FAILED = []


def check(name, got, want):
    if got == want:
        print("  ok    %s" % name)
    else:
        print("  FAIL  %s\n          got  %r\n          want %r" % (name, got, want))
        FAILED.append(name)


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def main():
    known = set(MODELS) | set(CHANGES)
    bare = N.bare_index(known)

    print("bare-name resolution")
    # The prefixed form is an OpenRouter convention. Matching only it made the
    # tool blind to every project calling a vendor SDK directly.
    check("bare name resolves to the full id",
          bare.get("gpt-5.2-chat"), "openai/gpt-5.2-chat")
    # A suffix two vendors share is skipped rather than guessed at - naming the
    # wrong vendor's model costs more than missing one.
    check("suffix shared by two vendors is dropped",
          "shared-suffix-9" in bare, False)
    # Short ids would collide with ordinary variable names.
    check("short names are not indexed", any(len(k) < 6 for k in bare), False)

    print("\nvendor-native spellings")
    # A vendor's own SDK does not use the catalogue's spelling. Anthropic ships
    # a dated id with dashes where the catalogue writes a dot, so a project
    # calling the vendor directly was invisible - which is most projects.
    norms = N.norm_index(known)
    check("a dated vendor id resolves to its catalogue entry",
          norms.get(N.normalize("claude-haiku-4-5-20251001")),
          "anthropic/claude-haiku-4.5")
    check("a bedrock id sheds its vendor prefix and revision",
          N.normalize("anthropic.claude-3-5-sonnet-20241022-v2:0"),
          "claude-3-5-sonnet")
    # The one thing this rule must never do is guess WHICH snapshot was meant.
    ambiguous = {"openai/gpt-4o", "openai/gpt-4o-2024-05-13",
                 "openai/gpt-4o-2024-08-06"}
    check("a rolling alias beside its own snapshots is dropped, not guessed",
          N.norm_index(ambiguous).get("gpt-4o"), None)

    root = tempfile.mkdtemp(prefix="nscheck-")
    try:
        print("\nscanning")
        write(root, "src/app.py", 'M = "openai/gpt-5-codex"\nB = "gpt-5.2-chat"\n')
        write(root, "Dockerfile", "ENV MODEL=mistralai/devstral-2512\n")
        write(root, "notebooks/x.ipynb",
              '{"cells":[{"source":["anthropic/claude-haiku-4.5"]}]}')
        write(root, "infra/main.tf", 'variable "m" { default = "openai/gpt-5.1" }')
        write(root, "node_modules/junk/a.js", 'const x = "openai/gpt-5-image";')
        write(root, "src/paths.py", 'P = "utils/helpers"\nT = "read-timeout-30"\n')

        write(root, "sdk/direct.py", 'M = "claude-haiku-4-5-20251001"\n')
        write(root, "sdk/noise.py",
              'A = "my-app-config-2024-01-01"\nB = "internal-service-v2"\n')

        found = N.scan(root, known, bare, norms)
        # A membership test, not an exact list: the notebook fixture spells the
        # same model out in full, and it is supposed to keep matching.
        check("finds a vendor-native dated id in source",
              os.path.join("sdk", "direct.py")
              in found.get("anthropic/claude-haiku-4.5", []), True)
        # Ordinary dashed strings that happen to carry a date or a revision must
        # not be dragged in by the same rules that strip those suffixes off a
        # real id. Asserted against the noise FILE rather than a total count,
        # because normalising adds files to models already found, not models.
        check("a dated config name is not a model",
              [m for m, fs in found.items()
               if any(f.endswith("noise.py") for f in fs)], [])

        found = N.scan(root, known, bare)
        # An extension filter cannot see a Dockerfile, and it found none of
        # these four the first time it was pointed at them.
        check("finds a prefixed id in source", "openai/gpt-5-codex" in found, True)
        check("finds a bare id in source", "openai/gpt-5.2-chat" in found, True)
        check("finds an id in a Dockerfile", "mistralai/devstral-2512" in found, True)
        check("finds an id in a notebook", "anthropic/claude-haiku-4.5" in found, True)
        check("finds an id in terraform", "openai/gpt-5.1" in found, True)
        # Vendored trees hold every model id in the world and none of them yours.
        check("skips node_modules", "openai/gpt-5-image" in found, False)
        # A directory path is not a model.
        check("ignores utils/helpers and read-timeout-30", len(found), 5)
        check("reports the file a hit came from",
              found["mistralai/devstral-2512"], ["Dockerfile"])

        # Two holes measured 2026-08-02 against how repositories really name a
        # model. Directories starting with a dot were ALL skipped, which took
        # .github with them - so a model pinned in a workflow was invisible in
        # the one place this tool's README tells people to run it. And ".env"
        # sat in the extension list without ever matching, because
        # os.path.splitext(".env") returns (".env", "") - the intent was
        # recorded and did nothing.
        write(root, ".github/workflows/ci.yml", "model: openai/gpt-5-codex\n")
        write(root, ".env", 'DEFAULT_MODEL="openai/gpt-5.1"\n')
        write(root, ".env.example", 'DEFAULT_MODEL="openai/gpt-5.1"\n')
        # Still skipped: dropping the blanket dot rule must not pull these in.
        write(root, ".venv/lib/j.py", 'M = "openai/gpt-5-image"\n')
        write(root, ".idea/j.py", 'M = "openai/gpt-5-image"\n')
        env_found = N.scan(root, known, bare)
        # A subset test, not an exact one: every case here shares a single
        # temporary tree, so earlier fixtures legitimately contribute paths.
        paths = {p.replace(os.sep, "/") for p in env_found.get("openai/gpt-5.1", [])}
        check("reads .env and .env.example",
              {".env", ".env.example"} <= paths, True)
        check("walks into .github",
              ".github/workflows/ci.yml" in
              [p.replace(os.sep, "/") for p in env_found.get("openai/gpt-5-codex", [])],
              True)
        check("still skips .venv and .idea",
              "openai/gpt-5-image" in env_found, False)

        # A file in another encoding used to be read with errors="ignore",
        # which DELETES the undecodable bytes and closes the gap - gluing
        # whatever sat on either side into a token nobody wrote. A scanner
        # that invents a finding is worse than one that misses a file.
        with open(os.path.join(root, "cp949.py"), "wb") as fh:
            fh.write(b'A = "openai/gpt-5'
                     + "한글".encode("cp949")
                     + b'-codex"\n')
        found2 = N.scan(root, known, bare)
        # The claim is about the cp949 file specifically: it must not appear,
        # because the id only exists there as two halves either side of bytes
        # that do not decode. Other fixtures in this shared tree spell the id
        # out properly and are supposed to match.
        check("bad bytes do not fabricate an id across the gap",
              any(p.replace(os.sep, "/").endswith("cp949.py")
                  for p in found2.get("openai/gpt-5-codex", [])),
              False)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\nverdicts")
    lvl, why, move = N.verdict("openai/gpt-5-codex", MODELS, CHANGES)
    check("a removed model is gone", lvl, "gone")
    # The claim is about THIS catalogue, not about every page a vendor keeps.
    # It used to read "no end-of-life date ever published", which asserted
    # knowledge of vendor documentation this has never read - and Anthropic's
    # own page proved it wrong.
    check("gone says the catalogue held no date, not that nobody published one",
          ("with no date in it beforehand" in why
           and "ever published" not in why), True)
    # The replacement is DATA. Folding it into the headline put terminal
    # indentation inside the --json detail field.
    check("replacement is returned separately", move["model"], "openai/gpt-5.1-codex")
    check("headline carries no layout", "\n" in why, False)

    lvl, _, move = N.verdict("mistralai/devstral-2512", MODELS, CHANGES)
    # Silence is the feature. Nothing in that vendor's line-up qualifies.
    check("no replacement is offered when none qualifies", (lvl, move), ("gone", None))

    lvl, why, _ = N.verdict("openai/gpt-5.2-chat", MODELS, CHANGES)
    check("a shutdown inside the window is soon", lvl, "soon")
    check("soon states the days left", "9 days left" in why, True)

    lvl, _, _ = N.verdict("anthropic/claude-haiku-4.5", MODELS, CHANGES)
    check("an unchanged model is ok", lvl, "ok")

    # Missing from the catalogue used to mean one sentence: "GONE, with no
    # end-of-life date ever published". It was applied to ids we had never
    # watched leave, which asserted a silent retirement that never happened and
    # contradicted the published record, where a delisted addressing variant is
    # deliberately NOT counted as a removal because the base model stayed.
    lvl, why, move = N.verdict("openai/gpt-5.1:batch", MODELS, CHANGES)
    check("a delisted variant is still a broken call", lvl, "gone")
    check("a delisted variant is not called a retirement",
          "no end-of-life date ever published" in why, False)
    check("a delisted variant points at its own base",
          (move["model"], move["kind"]), ("openai/gpt-5.1", "same_model_base"))
    # Same model, same price - there is no before-and-after to compare.
    check("a delisted variant quotes no former price",
          move["gone_price_per_million_output"], None)
    check("the base price is per million, not per token",
          move["price_per_million_output"], 10.0)

    lvl, why, move = N.verdict("ghost/never-seen-go", MODELS, CHANGES)
    check("an id we never watched leave is still flagged", lvl, "gone")
    check("and says so honestly instead of claiming a removal",
          "we have no record of it leaving" in why, True)
    check("and invents no replacement", move, None)

    print("\nvendor-published retirements")
    # The catalogue carries no end-of-life date for any Anthropic model, and
    # Anthropic publishes them on its own docs. This returned "ok" for
    # claude-opus-4.1 two days before its vendor retires it - a clean bill and
    # exit 0 on the code CI depends on.
    soon = (dt.date.today() + dt.timedelta(days=2)).isoformat()
    past = (dt.date.today() - dt.timedelta(days=40)).isoformat()
    vend = dict(CHANGES)
    vend["anthropic/claude-haiku-4.5"] = [{
        "type": "VENDOR_DEPRECATION", "expires_on": soon, "vendor_status": "deprecated",
        "replacement": {"model": "claude-opus-4-8", "kind": "vendor_stated"}}]
    vend["openai/gpt-5.1"] = [{
        "type": "VENDOR_DEPRECATION", "expires_on": past, "vendor_status": "retired"}]

    lvl, why, move = N.verdict("anthropic/claude-haiku-4.5", MODELS, vend)
    check("a vendor date the catalogue lacks is still a warning", lvl, "soon")
    check("and it says the date is not the catalogue's", "not in the catalogue" in why, True)
    check("and carries the replacement the vendor itself named",
          (move["model"], move["kind"]), ("claude-opus-4-8", "vendor_stated"))
    # Retired upstream while the catalogue still lists it is neither gone nor
    # fine, and which of the two sources disagrees is the useful part.
    lvl, why, _ = N.verdict("openai/gpt-5.1", MODELS, vend)
    check("retired upstream but still listed is not called gone", lvl, "soon")
    check("and names the disagreement", "the catalogue still lists it" in why, True)
    # An Active row's date column reads "not sooner than X" - a floor on
    # lifetime, not a plan to remove. It must never reach a verdict.
    check("a model with no vendor row is untouched",
          N.verdict("openai/gpt-5.1-codex", MODELS, vend)[0], "ok")

    print("\ntransfer")
    # The catalogue is 178KB in the clear and 14KB gzipped, measured against
    # the live host. urllib sends no Accept-Encoding and never decompresses, so
    # every run pulled the full copy. Asking is not receiving, though: a proxy
    # or a future host may answer in the clear, and assuming otherwise turns a
    # saving into a crash. The RESPONSE header decides.
    class FakeResponse:
        def __init__(self, body, encoding=None):
            self._b, self.headers = body, {"Content-Encoding": encoding} if encoding else {}

        def read(self):
            return self._b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    payload = json.dumps({"models": {"a/b": {}}}).encode("utf-8")
    real = N.urllib.request.urlopen
    try:
        N.urllib.request.urlopen = lambda *a, **k: FakeResponse(
            gzip.compress(payload), "gzip")
        check("a gzipped response is decompressed",
              N.fetch("https://example.invalid/x"), {"models": {"a/b": {}}})
        N.urllib.request.urlopen = lambda *a, **k: FakeResponse(payload)
        check("a plain response is not run through gzip",
              N.fetch("https://example.invalid/x"), {"models": {"a/b": {}}})
    finally:
        N.urllib.request.urlopen = real

    print("\nformatting")
    check("cheap prices keep three decimals", N.money(0.013), "$0.013")
    check("normal prices keep two", N.money(10.0), "$10.00")
    check("a missing price is not rendered as zero", N.money(None), "?")

    print()
    if FAILED:
        print("FAILED %d of the checks above" % len(FAILED))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

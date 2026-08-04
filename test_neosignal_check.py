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
    # Nine days out FROM TODAY, not a fixed date. It was 2026-08-10 with a
    # matching days_left of 9 in CHANGES, which made two problems: the check
    # below pinned the stale stored countdown that verdict() no longer reads,
    # and the fixture would have changed meaning on 2026-08-10 when the date
    # went past and the model became a different case entirely.
    "openai/gpt-5.2-chat": {"context_length": 128000,
                            "expiration_date": (dt.date.today()
                                                + dt.timedelta(days=9)).isoformat(),
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
    # days_left deliberately WRONG here. verdict() counts from the date now,
    # and a fixture that agrees with a value the code must ignore cannot show
    # that it is ignoring it.
    "openai/gpt-5.2-chat": [{"type": "DEPRECATION_DEADLINE", "days_left": 99,
                             "expires_on": (dt.date.today()
                                            + dt.timedelta(days=9)).isoformat()}],
    "anthropic/claude-haiku-4.5": [],
    # An addressing variant that left the catalogue while its base model stayed.
    # Deliberately carries NO removal record, because the pipeline classifies a
    # variant delisting as a catalogue change rather than a retirement.
    "openai/gpt-5.1:batch": [{"type": "PRICING_CHANGE", "date": "2026-07-20"}],
    # Known to us, absent from the catalogue, never observed leaving.
    "ghost/never-seen-go": [{"type": "PRICING_CHANGE", "date": "2026-07-11"}],
}

FAILED = []
RAN = []


def check(name, got, want):
    RAN.append(name)
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

        # Measured against a real 391,000-file repository: the walk selected
        # 21,590 files totalling 1,490 MB and the scan did not finish in ten
        # minutes. It completes in four and a half with a one-megabyte cap.
        # The cap must be visible, because a limit nobody is told about reads
        # as coverage.
        write(root, "src/huge.py", 'M = "openai/gpt-5.1"\n' + "# pad\n" * 400000)
        capped = N.scan(root, known, bare)
        check("a file over the cap is not read",
              any(f.endswith("huge.py")
                  for f in capped.get("openai/gpt-5.1", [])), False)
        check("and the skip is counted rather than silent",
              any(p.endswith("huge.py") for p in getattr(N.scan, "skipped", [])), True)

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
    # The stored days_left says 99 and must not appear. This is the defect that
    # shipped: the countdown was read from the event rather than counted, so
    # two models carrying the same date printed different numbers.
    check("and counts it rather than reading the stored value",
          "99" in why, False)

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
    # A month-old reading presented exactly like this morning's is the quiet
    # staleness this tool exists to catch elsewhere. The collector keeps its
    # last good copy when a vendor page breaks, which is right, so the age has
    # to be visible.
    old = dict(vend)
    old["openai/gpt-5.1"] = [dict(vend["openai/gpt-5.1"][0],
                                  checked=(dt.date.today() - dt.timedelta(days=40)).isoformat())]
    _, why_old, _ = N.verdict("openai/gpt-5.1", MODELS, old)
    check("a stale vendor reading says how old it is",
          "vendor page last read 40 days ago" in why_old, True)
    fresh = dict(vend)
    fresh["openai/gpt-5.1"] = [dict(vend["openai/gpt-5.1"][0],
                                    checked=dt.date.today().isoformat())]
    _, why_new, _ = N.verdict("openai/gpt-5.1", MODELS, fresh)
    check("a fresh one stays quiet about it", "last read" in why_new, False)
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

    print("\nthe exit-2 contract")
    # "could not check" must never leave as a pass. Exercised through main()
    # rather than fetch(), because the exit code is the thing being promised
    # and it is decided there.
    import argparse

    def run_with(fetch_impl):
        # stderr as well as stdout: the tool writes the "not a pass" line to
        # stderr, so capturing only stdout would have shown an empty string
        # and made this test look like a defect in the tool.
        real_fetch, real_argv = N.fetch, sys.argv
        out = io.StringIO()
        real_out, real_err = sys.stdout, sys.stderr
        try:
            N.fetch = fetch_impl
            sys.argv = ["neosignal_check.py", "."]
            sys.stdout = sys.stderr = out
            return N.main(), out.getvalue()
        finally:
            N.fetch, sys.argv = real_fetch, real_argv
            sys.stdout, sys.stderr = real_out, real_err

    def unreachable(url):
        raise N.urllib.error.URLError("no route")

    def not_json(url):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")

    code, said = run_with(unreachable)
    check("an unreachable host exits 2, not 0", code, 2)
    check("and says nothing was checked", "NOT a pass" in said, True)

    # HTTP 200 with a body that is not JSON - a CDN error page, a truncated
    # response. The dangerous one, because the request succeeded.
    code, said = run_with(not_json)
    check("a 200 with an unusable body also exits 2", code, 2)
    check("and says so too", "NOT a pass" in said, True)

    print("\nspellings that were being missed silently")
    # Each of these was measured as a miss on 2026-08-03 against the live
    # catalogue, before the rules below were changed. None raised an error -
    # the tool said "no model ids from the catalogue appear" and exited 0,
    # which reads exactly like a clean bill of health.
    real = {"openai/gpt-4", "openai/gpt-5", "microsoft/phi-4", "z-ai/glm-5",
            "qwen/qwen3.5-27b", "meta-llama/llama-3.3-70b-instruct",
            "amazon/nova-pro-v1", "anthropic/claude-haiku-4.5"}
    rb, rn = N.bare_index(real), N.norm_index(real)

    def resolve(tok):
        if tok in real:
            return tok
        return rb.get(tok.lower()) or rn.get(N.normalize(tok))

    # The most common way anyone names a model in code. The minimum length was
    # 6 and these are 5, so a file containing nothing but `model="gpt-4"`
    # reported a clean bill - the first thing a sceptical reader would try.
    #
    # These go through scan() rather than the indexes directly, because the
    # length floor is applied in scan BEFORE either index is consulted. Asking
    # the indexes on their own answers correctly whichever floor is set, so a
    # test written that way passes against the broken version too - which is
    # exactly what the first draft of this block did.
    tmp = tempfile.mkdtemp()
    try:
        write(tmp, "app/a.py", 'r = client.create(model="gpt-4")\n')
        write(tmp, "app/b.py", 'r = client.create(model="gpt-5")\n')
        write(tmp, "app/c.py", 'M = "phi-4"\nN = "glm-5"\n')
        write(tmp, "app/d.py", 'X = "utf-8"\nY = "node-20"\nZ = "read-timeout-30"\n')
        seen = N.scan(tmp, real, rb, rn)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    check("gpt-4 written bare is found by a scan", "openai/gpt-4" in seen, True)
    check("gpt-5 written bare is found by a scan", "openai/gpt-5" in seen, True)
    check("phi-4 written bare is found by a scan", "microsoft/phi-4" in seen, True)
    check("glm-5 written bare is found by a scan", "z-ai/glm-5" in seen, True)
    check("and the scan invents nothing else", len(seen), 4)

    # Bedrock writes Meta's family without the separator the catalogue uses.
    check("bedrock's meta spelling folds to the catalogue id",
          resolve("meta.llama3-3-70b-instruct-v1:0"),
          "meta-llama/llama-3.3-70b-instruct")

    # A dotted VERSION is not a vendor prefix. Reading it as one removed the
    # first segment of every dotted Qwen id in the catalogue - 19 of them -
    # leaving forms like `5-27b` that nothing could ever match.
    check("a dotted version is not read as a vendor prefix",
          resolve("qwen3.5-27b"), "qwen/qwen3.5-27b")
    check("and its dashed sdk spelling lands on the same model",
          resolve("qwen3-5-27b"), "qwen/qwen3.5-27b")

    # The spellings that already worked have to keep working; both depend on
    # the vendor-prefix rule that was narrowed above.
    check("bedrock's amazon spelling still resolves",
          resolve("amazon.nova-pro-v1:0"), "amazon/nova-pro-v1")
    check("anthropic's dated sdk spelling still resolves",
          resolve("claude-haiku-4-5-20251001"), "anthropic/claude-haiku-4.5")

    # Lowering the floor must not start matching things that are not models.
    # Nothing is reported unless it resolves to exactly one catalogue id, and
    # that is what does the work the length rule used to be credited with.
    check("a short hyphenated token that is not a model stays unmatched",
          resolve("utf-8"), None)
    check("a version string is not a model", resolve("node-20"), None)

    print("\nthe platform a spelling belongs to")
    # A retirement date belongs to a model ON A PLATFORM. Anthropic retired
    # claude-3-haiku on 2026-04-20; AWS Bedrock serves it to 2026-09-10. Both
    # spellings resolve to one catalogue id, and the normalisation that makes
    # that work is what throws away the only signal that says which date is
    # the reader's.
    check("a bedrock id is recognised as bedrock",
          N.platform_of("anthropic.claude-3-haiku-20240307-v1:0"), "AWS Bedrock")
    check("a vendor-native dated pin is not a platform",
          N.platform_of("claude-3-haiku-20240307"), None)
    check("an openrouter id is not a platform",
          N.platform_of("anthropic/claude-3-haiku"), None)
    check("a bare name is not a platform", N.platform_of("gpt-4"), None)

    plat = {"anthropic/claude-3-haiku": [
        {"platform": "AWS Bedrock", "end_of_life": "2099-09-10",
         "source": "https://example.invalid/lifecycle"}]}
    ch = {"anthropic/claude-3-haiku": [
        {"type": "VENDOR_DEPRECATION", "expires_on": "2024-04-20"}]}
    mods = {"anthropic/claude-3-haiku": {}}

    lvl, why, _ = N.verdict("anthropic/claude-3-haiku", mods, ch,
                            ["AWS Bedrock"], plat)
    check("a bedrock caller is given the bedrock date", "2099-09-10" in why, True)
    check("and told the vendor's date differs", "2024-04-20" in why, True)
    check("which is not an alarm, because it is far off", lvl, "moved")

    lvl, why, _ = N.verdict("anthropic/claude-3-haiku", mods, ch, None, plat)
    check("a vendor-native caller keeps the vendor date", "2024-04-20" in why, True)
    check("and is warned, because that date has passed", lvl, "soon")

    # The guard that took two attempts. Tracking only the platforms seen gave
    # {"AWS Bedrock"} for a tree calling a model BOTH ways, so "exactly one
    # platform" passed and the file calling Anthropic directly was told a
    # deadline five months later than its own. None has to be in the set.
    tmp = tempfile.mkdtemp()
    try:
        write(tmp, "aws/a.js", 'modelId: "anthropic.claude-3-haiku-20240307-v1:0"\n')
        write(tmp, "direct/b.py", 'model = "claude-3-haiku-20240307"\n')
        real = {"anthropic/claude-3-haiku"}
        N.scan(tmp, real, N.bare_index(real), N.norm_index(real))
        mixed = getattr(N.scan, "platforms", {})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    check("a tree spelling it both ways claims no platform",
          mixed.get("anthropic/claude-3-haiku"), None)

    tmp = tempfile.mkdtemp()
    try:
        write(tmp, "aws/a.js", 'modelId: "anthropic.claude-3-haiku-20240307-v1:0"\n')
        real = {"anthropic/claude-3-haiku"}
        N.scan(tmp, real, N.bare_index(real), N.norm_index(real))
        only = getattr(N.scan, "platforms", {})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    check("a tree spelling it one way claims that platform",
          only.get("anthropic/claude-3-haiku"), ["AWS Bedrock"])

    # A consumer keying on "whose deadline is this" should not have to read an
    # English sentence to find out. The file already makes this argument about
    # `replacement`; the platform answer arrived in prose only.
    # verdict fills a dict the caller owns. It briefly returned a fourth element
    # on this branch only, so its arity depended on which path it took - and
    # the checks above, which unpack three, broke the moment a platform
    # answered. A function whose shape varies by branch is a trap for whoever
    # writes the next caller.
    extra = {}
    lvl, why, _ = N.verdict("anthropic/claude-3-haiku", mods, ch,
                            ["AWS Bedrock"], plat, extra)
    check("verdict still returns exactly three", (lvl, why) is not None, True)
    check("naming the platform", extra.get("platform"), "AWS Bedrock")
    check("its date", extra.get("platform_end_of_life"), "2099-09-10")
    check("the vendor's differing date", extra.get("vendor_end_of_life"), "2024-04-20")
    check("and where it was read from",
          extra.get("source"), "https://example.invalid/lifecycle")
    plain = {}
    N.verdict("anthropic/claude-3-haiku", mods, ch, None, plat, plain)
    check("a vendor verdict fills nothing", plain, {})

    print("\nprovider-prefixed spellings")
    # LiteLLM and friends put the ROUTE in front of the model - azure/gpt-4o,
    # bedrock/anthropic.claude-3-haiku-20240307-v1:0, vertex_ai/gemini-2.5-pro,
    # together_ai/meta-llama/llama-3.3-70b-instruct. Measured 2026-08-04: all
    # four already resolve, through the bare-name and normalise routes rather
    # than by anything that knows what a provider prefix is.
    #
    # Pinned because nothing was protecting it. Asking the resolvers directly
    # says azure/gpt-4o MISSES - the whole string is not a bare name - and that
    # is the wrong probe: the scanner extracts `gpt-4o` from inside it. Testing
    # at the wrong layer is how a working feature gets "fixed".
    lite = {"openai/gpt-4o", "anthropic/claude-3-haiku",
            "google/gemini-2.5-pro", "meta-llama/llama-3.3-70b-instruct"}
    tmp = tempfile.mkdtemp()
    try:
        write(tmp, "app.py",
              'A = "azure/gpt-4o"\n'
              'B = "bedrock/anthropic.claude-3-haiku-20240307-v1:0"\n'
              'C = "vertex_ai/gemini-2.5-pro"\n'
              'D = "together_ai/meta-llama/llama-3.3-70b-instruct"\n')
        seen = N.scan(tmp, lite, N.bare_index(lite), N.norm_index(lite))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for want in sorted(lite):
        check("litellm-style route prefix resolves %s" % want.split("/")[-1],
              want in seen, True)
    check("and the prefix invents nothing extra", len(seen), 4)

    print("\na date the vendor took back")
    # Measured 2026-08-04: Google carried 2026-10-16 for gemini-2.5-pro,
    # gemini-2.5-flash and gemini-2.5-flash-lite, and its page now carries
    # nothing for any of them. Anyone who ran this last week was told to
    # migrate by October; the next run said "no change recorded" and explained
    # nothing. A model losing its deadline is as worth knowing as gaining one.
    pulled = {"google/gemini-2.5-pro": {"model": "google/gemini-2.5-pro",
                                        "had": "2026-10-16",
                                        "noticed": "2026-08-03"}}
    wmods = {"google/gemini-2.5-pro": {}}
    wextra = {}
    lvl, why, _ = N.verdict("google/gemini-2.5-pro", wmods, {}, None, None,
                            wextra, pulled)
    check("a withdrawn date is reported, not swallowed", "2026-10-16" in why, True)
    check("and says the date is gone rather than due",
          "withdrawn" in why and "days left" not in why, True)
    check("not an alarm - there is no deadline to miss", lvl, "moved")
    check("the date is structured too", wextra.get("withdrawn_date"), "2026-10-16")
    check("with the day it was noticed",
          wextra.get("withdrawn_noticed"), "2026-08-03")
    # A model nobody withdrew anything from must be untouched by this path.
    lvl, why, _ = N.verdict("anthropic/claude-haiku-4.5", MODELS, CHANGES,
                            None, None, {}, pulled)
    check("a model with no withdrawal is unaffected", lvl, "ok")

    print("\nretired by the vendor and already delisted")
    # The case old code actually hits, and the one this tool was silent about
    # until 2026-08-04. The catalogue diff starts at its first snapshot, so it
    # can never reach a model that left before that - but the vendor's own page
    # reaches back years, and 187 of those entries were being collected daily
    # and discarded because the merge keyed on catalogue ids.
    #
    # Measured the same day: claude-3-opus, claude-3-5-sonnet-20241022 and
    # gemini-2.0-flash are all still referenced in real trees, and all three
    # produced "no change recorded".
    delisted = {"anthropic/claude-3-opus": {"retires_on": "2026-01-05",
                                            "vendor_id": "claude-3-opus-20240229",
                                            "source": "https://docs.claude.com/x"}}
    lvl, why, move = N.verdict("anthropic/claude-3-opus", MODELS, {},
                               None, None, {}, None, delisted)
    check("a delisted model with a vendor date is GONE, not unknown", lvl, "gone")
    check("and the date is the vendor's", "2026-01-05" in why, True)
    # The key has to be the normalised form for anything to match it, so the id
    # on screen can be a spelling nobody wrote. The vendor's own is named.
    check("the vendor's own spelling is named when it differs",
          "claude-3-opus-20240229" in why, True)
    # Without the record it must still say the honest thing rather than guess.
    lvl2, why2, _ = N.verdict("anthropic/claude-3-opus", MODELS, {},
                              None, None, {}, None, {})
    check("with no record at all it stays 'no record of it leaving'",
          "no record of it leaving" in why2, True)

    # Tense follows the DATE. 38 of the 187 published records carried a
    # retirement date in the FUTURE, and the line read "its vendor retired it
    # on 2026-08-05" on 2026-08-04 - a false statement about a model that had
    # not retired yet. Found by running the tool over a third-party repository
    # and noticing it contradicted what the same tool said that morning.
    ahead = (dt.date.today() + dt.timedelta(days=40)).isoformat()
    behind = (dt.date.today() - dt.timedelta(days=40)).isoformat()
    _l, why_f, _ = N.verdict("anthropic/claude-3-opus", MODELS, {}, None, None, {},
                             None, {"anthropic/claude-3-opus": {"retires_on": ahead}})
    check("a future date is not spoken of in the past", "retired it on" in why_f, False)
    check("and it says the model is not in the catalogue, not that it left",
          "retires it on" in why_f and "is not in the catalogue" in why_f, True)
    _l, why_p, _ = N.verdict("anthropic/claude-3-opus", MODELS, {}, None, None, {},
                             None, {"anthropic/claude-3-opus": {"retires_on": behind}})
    check("a past date still reads as past", "retired it on" in why_p, True)

    # SEVERITY follows the date as well, and fixing only the wording left this
    # wrong: 23 of 173 records were more than a month out and every one was
    # reported GONE - including one whose vendor serves it until 2028. GONE
    # means you cannot call this any more. A year of runway is information.
    far = (dt.date.today() + dt.timedelta(days=400)).isoformat()
    near = (dt.date.today() + dt.timedelta(days=10)).isoformat()
    lvl_far, _w, _ = N.verdict("anthropic/claude-3-opus", MODELS, {}, None, None, {},
                               None, {"anthropic/claude-3-opus": {"retires_on": far}})
    lvl_near, _w, _ = N.verdict("anthropic/claude-3-opus", MODELS, {}, None, None, {},
                                None, {"anthropic/claude-3-opus": {"retires_on": near}})
    lvl_past, _w, _ = N.verdict("anthropic/claude-3-opus", MODELS, {}, None, None, {},
                                None, {"anthropic/claude-3-opus": {"retires_on": behind}})
    check("a year of runway is not an emergency", lvl_far, "moved")
    check("ten days out is", lvl_near, "soon")
    check("and a date already past is gone", lvl_past, "gone")

    print("\nthe case you wrote it in")
    # `GPT-4` resolved and `GPT-4o` did not, and which one you got depended on
    # something invisible: the bare index matched case exactly, the normalising
    # index did not, and a model lives in one or the other. `gpt-4o` collides
    # with its own dated snapshots, so it is dropped from the normalising index
    # and reachable only through the bare one - write it the way most of the
    # world writes it and the tool said nothing.
    #
    # Measured 2026-08-04 across four repository trees: 220 occurrences of
    # `GPT-4o`, 81 of `GPT-4o-mini`, every one silent. Fixing it gained exactly
    # those three spellings and lost nothing.
    #
    # This direction is the dangerous one. A false positive argues with you.
    # A miss prints a clean bill.
    # The catalogue pair matters and a first version of this test got it wrong.
    # Written against a model that still has a normalising route, the check
    # passes with the case fix REMOVED - because that route folds case anyway,
    # so it proves nothing. The defect only exists for a model the normalising
    # index has dropped, which is why the rolling alias and one of its own dated
    # snapshots are both here: they normalise to the same form, collide, and
    # leave the bare index as the only way in.
    case_known = {"openai/gpt-4o", "openai/gpt-4o-2024-05-13"}
    case_bare = N.bare_index(case_known)
    case_norm = N.norm_index(case_known)
    check("the rolling alias has no normalising route", "gpt-4o" in case_norm, False)
    case_root = tempfile.mkdtemp(prefix="nscase-")
    try:
        write(case_root, "cfg.py", 'A = "GPT-4o"\n')
        write(case_root, "other.py", 'B = "gpt-4o"\n')
        got = N.scan(case_root, case_known, case_bare, case_norm)
        check("upper and lower are the same model",
              sorted(got), ["openai/gpt-4o"])
        check("and both files are reported against it",
              len(got.get("openai/gpt-4o", [])), 2)
    finally:
        shutil.rmtree(case_root, ignore_errors=True)

    print("\nhugging face repository ids")
    # Never designed for, and already working - found on 2026-08-04 by resolving
    # every candidate token out of four large repository trees and reading what
    # came back. A quarter of the unusual-looking resolutions were HF ids.
    #
    # Pinned because it is undocumented, and undocumented behaviour is what
    # somebody deletes. What it actually rests on is case folding in the
    # normalise path: drop the lowercasing there, or disable that path, and
    # this check fails. Both were tried.
    #
    # (The sweep also tempted a rule rejecting mixed-case path prefixes, on the
    # grounds that `sha512-KhYd2Hjt/O1` has one and so do `Qwen` and
    # `MiniMaxAI`. It was NOT added, and this test would not have caught it:
    # the bare component of a HuggingFace id resolves on its own, without the
    # prefix. The rule was dropped because nothing measured needs it - the one
    # token that motivated it sits in a .eml mail backup, an extension this
    # tool does not read.)
    hf_root = tempfile.mkdtemp(prefix="nshf-")
    try:
        write(hf_root, "load.py",
              'from transformers import AutoModel\n'
              'A = "Qwen/Qwen3-30B-A3B-Instruct-2507"\n'
              'B = "MiniMaxAI/MiniMax-M2.5"\n'
              'C = "Gryphe/MythoMax-L2-13b"\n')
        hf_known = {"qwen/qwen3-30b-a3b-instruct-2507", "minimax/minimax-m2.5",
                    "gryphe/mythomax-l2-13b"}
        got = N.scan(hf_root, hf_known, N.bare_index(hf_known),
                     N.norm_index(hf_known))
        check("an uppercase vendor prefix still resolves",
              sorted(got), sorted(hf_known))
    finally:
        shutil.rmtree(hf_root, ignore_errors=True)

    print("\nthings that look like a model id and are not")
    # Every string below was found in real files on 2026-08-04 by grepping four
    # unrelated repositories for a vendor/name shape. Not one is a model
    # reference: they are npm scoped packages, GitHub issue references, C++
    # include paths and protobuf imports. A looser matcher reports all of them,
    # and a tool that cries wolf on `#include "google/protobuf/..."` gets
    # deleted within a minute of being run - which is the entire reason this
    # matches against the catalogue instead of against a pattern.
    #
    # The positive control at the end is not decoration. Without it this whole
    # section passes just as well when scanning is broken and nothing at all is
    # found, which is the shape of a test that guards nothing.
    decoy_root = tempfile.mkdtemp(prefix="nsdecoy-")
    try:
        write(decoy_root, "update.ps1",
              "# keep @openai/codex on the latest npm version\n"
              "$before = (& $npm ls -g '@openai/codex' --depth=0)\n")
        write(decoy_root, "watchdog.ps1",
              "# WHY: openai/codex#22004 - Codex desktop crashes when a rollout\n")
        write(decoy_root, "port.h",
              '#define GTEST_PROJECT_URL_ "https://github.com/google/googletest/"\n'
              '#include "google/protobuf/util/json_util.h"\n')
        write(decoy_root, "svc.proto",
              'import "google/protobuf/empty.proto";\n'
              'import "google/protobuf/wrappers.proto";\n')
        write(decoy_root, "gtest.cc",
              "// https://github.com/google/googletest/blob/main/docs/advanced.md\n")

        decoys = N.scan(decoy_root, known, bare, N.norm_index(known))
        check("an npm scoped package is not its vendor's model",
              "openai/gpt-5-codex" in decoys, False)
        check("a github issue reference is not a model", decoys, {})

        # Same tree, one real reference added. If this does not appear, the
        # emptiness above proved nothing.
        write(decoy_root, "agent.py", 'M = "openai/gpt-5-codex"\n')
        with_real = N.scan(decoy_root, known, bare, N.norm_index(known))
        check("a real id in the same tree is still found",
              "openai/gpt-5-codex" in with_real, True)
        check("and it is the ONLY thing found there", len(with_real), 1)

        # The catalogue really does sell models called `auto` and `free`.
        # normalize() folds `a/b/c` down to `c`, so before 2026-08-04 every
        # `billing/free` and `apis/edgecontainer/v1/auto` in a tree resolved to
        # one - found by running the tool over a Google Cloud SDK checkout,
        # where it reported both across four files. A local catalogue here on
        # purpose: this needs ids the shared fixture does not have, and adding
        # them there would move counts in unrelated checks.
        words = {"openrouter/auto", "openrouter/free", "openai/gpt-5.1"}
        wbare, wnorm = N.bare_index(words), N.norm_index(words)
        word_root = tempfile.mkdtemp(prefix="nsword-")
        try:
            write(word_root, "paths.py",
                  'ROUTE = "apis/edgecontainer/v1/auto"\nTIER = "billing/free"\n')
            check("an ordinary path segment is not a model",
                  N.scan(word_root, words, wbare, wnorm), {})
            # And the id itself, spelled out, still resolves - the fix drops a
            # folding route, not the model.
            write(word_root, "real.py", 'M = "openrouter/auto"\n')
            check("but the id spelled in full still resolves",
                  "openrouter/auto" in N.scan(word_root, words, wbare, wnorm), True)
        finally:
            shutil.rmtree(word_root, ignore_errors=True)

        # An npm integrity hash. Base64 carries a slash, so the tail of one is
        # a path segment as far as spelling resolution is concerned, and
        # `sha512-KhYd2Hjt/O1` resolved on its last two characters to
        # `openai/o1`. Found in a real package-lock.json in this workspace.
        #
        # The length rule was being applied to the raw token, which is 19
        # characters here, rather than to the part that actually matched. Base64
        # has no hyphen, so a lockfile can only manufacture SHORT names this way
        # - and every JavaScript repository ships a lockfile.
        hashy = {"openai/o1", "openai/gpt-4o"}
        hbare, hnorm = N.bare_index(hashy), N.norm_index(hashy)
        lock_root = tempfile.mkdtemp(prefix="nslock-")
        try:
            # The `+` matters and the first version of this test did not have
            # it: base64 padding and `+` are outside the token pattern, so they
            # are what CUTS the hash down to `sha512-KhYd2Hjt/O1`. Written as
            # one unbroken run the token normalises to `o-1abcdefgh`, matches
            # nothing, and the test passes whether the guard is there or not.
            write(lock_root, "package-lock.json",
                  '{"integrity": "sha512-KhYd2Hjt/O1+Kw=="}\n')
            check("an integrity hash does not resolve on its tail",
                  N.scan(lock_root, hashy, hbare, hnorm), {})
            write(lock_root, "client.py", 'MODEL = "openai/o1"\n')
            found = N.scan(lock_root, hashy, hbare, hnorm)
            check("the same id written out is still found",
                  "openai/o1" in found, True)
            check("and only from the file that really says it",
                  [os.path.basename(p) for p in found.get("openai/o1", [])],
                  ["client.py"])
        finally:
            shutil.rmtree(lock_root, ignore_errors=True)
    finally:
        shutil.rmtree(decoy_root, ignore_errors=True)

    print("\nprogress while the walk is quiet")
    # Measured 2026-08-04 against a 1,334-file tree: the tool printed NOTHING
    # for 23 minutes and then answered. Nobody waits that long at a prompt with
    # a blank screen - they conclude it is broken and kill it, which is a worse
    # failure than being slow. But the cure can break the tool's other contract,
    # so all four of these are pinned together: the reassurance has to reach a
    # human without ever touching stdout, because `--json | jq` and `> file`
    # have to keep working, and --quiet has to stay quiet.
    prog_root = tempfile.mkdtemp(prefix="nsprog-")
    try:
        for i in range(6):
            write(prog_root, "m%d.py" % i, 'M = "anthropic/claude-haiku-4.5"\n')

        class _TTY(io.StringIO):
            def isatty(self):
                return True

        class _Pipe(io.StringIO):
            def isatty(self):
                return False

        def run_cli(argv, err_cls):
            out, err = io.StringIO(), err_cls()
            real = (sys.stdout, sys.stderr, sys.argv, N.fetch)
            sys.stdout, sys.stderr, sys.argv = out, err, ["check"] + argv
            # No network, per this file's rule. main() is the thing under test
            # here - the progress line lives in it, not in scan().
            N.fetch = lambda url: ({"models": MODELS} if url == N.MODELS_URL
                                   else {"changes": CHANGES})
            try:
                try:
                    N.main()
                except SystemExit:
                    pass
            finally:
                sys.stdout, sys.stderr, sys.argv, N.fetch = real
            return out.getvalue(), err.getvalue()

        tty_out, tty_err = run_cli([prog_root], _TTY)
        check("a terminal is told the walk is running", "reading" in tty_err, True)
        check("and stdout is never where that goes", "\r" in tty_out, False)

        json_out, json_err = run_cli([prog_root, "--json"], _TTY)
        ok_json = True
        try:
            json.loads(json_out)
        except ValueError:
            ok_json = False
        check("--json stdout still parses with progress on", ok_json, True)
        check("because the progress went to stderr", "reading" in json_err, True)

        _, pipe_err = run_cli([prog_root], _Pipe)
        check("a pipe or a log file gets none of it", "reading" in pipe_err, False)

        _, quiet_err = run_cli([prog_root, "--quiet"], _TTY)
        check("--quiet means quiet", "reading" in quiet_err, False)
    finally:
        shutil.rmtree(prog_root, ignore_errors=True)

    print("\nformatting")
    check("cheap prices keep three decimals", N.money(0.013), "$0.013")
    check("normal prices keep two", N.money(10.0), "$10.00")
    check("a missing price is not rendered as zero", N.money(None), "?")

    print()
    if FAILED:
        print("FAILED %d of %d checks" % (len(FAILED), len(RAN)))
        return 1
    # The COUNT, not just the word. A pass line counts only what ran, so a
    # section that dies early - or never gets reached because something above
    # it raised - reports "all checks passed" while a third of the suite never
    # executed. The number is the only thing in this output that can show that,
    # and the exit code is the only thing a script should read.
    print("all %d checks passed" % len(RAN))
    return 0


if __name__ == "__main__":
    sys.exit(main())

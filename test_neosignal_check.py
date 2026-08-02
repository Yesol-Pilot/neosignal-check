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

import io
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
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\nverdicts")
    lvl, why, move = N.verdict("openai/gpt-5-codex", MODELS, CHANGES)
    check("a removed model is gone", lvl, "gone")
    check("gone says no date was ever published",
          "no end-of-life date ever published" in why, True)
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

# neosignal-check

Find out which AI models your code calls that are **already gone**.

```
curl -sO https://neosignal-ai.vercel.app/check.py
python check.py .
```

```
3 models referenced in .

  ok     anthropic/claude-haiku-4.5    no change recorded
  GONE   openai/gpt-5-codex            GONE from the catalogue on 2026-07-30,
                                       with no end-of-life date ever published
         nearest still listed: openai/gpt-5.1-codex at $10.00 per million
         output, against the $10.00 it cost
         src/agent.ts
  SOON   openai/gpt-5.2-chat           shuts down 2026-08-10 - 9 days left
         src/agent.ts

2 need attention.
```

No key, no signup, no account, no dependencies. One stdlib Python file that
reads two public JSON endpoints.

## What it has actually caught

Not a mock. Every row below left the catalogue on the date shown, and **not one
of them had an end-of-life date published anywhere** - which is exactly why a
deprecation calendar could not have warned you.

<!--evidence:start-->
| vanished | model | end-of-life date published? | nearest still listed |
|---|---|---|---|
| 2026-08-01 | `openai/gpt-5.1-chat` | **none, ever** | `openai/gpt-5.1` |
| 2026-08-01 | `mistralai/devstral-2512` | **none, ever** | _nothing qualifies_ |
| 2026-07-30 | `openai/o4-mini-deep-research` | **none, ever** | _nothing qualifies_ |
| 2026-07-30 | `openai/o3-deep-research` | **none, ever** | _nothing qualifies_ |
| 2026-07-30 | `openai/gpt-5-codex` | **none, ever** | `openai/gpt-5.1-codex` |

As of 2026-08-02.
<!--evidence:end--> The live list is always at
[neosignal-ai.vercel.app/gone.html](https://neosignal-ai.vercel.app/gone.html),
and the raw records are in
[`/api/changes.json`](https://neosignal-ai.vercel.app/api/changes.json) if you
would rather check the claim than take it.

Where the last column says nothing qualifies, that is the tool declining to
guess. It names a replacement only when the two ids visibly sit in the same
vendor line.

## The number that explains why this exists

Measured against the live catalogue, and checkable from
[`/api/models.json`](https://neosignal-ai.vercel.app/api/models.json) in one
request:

<!--stat:start-->
| | |
|---|---|
| models carrying a published end-of-life date | **5 of 337** |
| vendors that publish one at all | **2 of 58** |

**98.5% of models have no shutdown date anywhere.**
<!--stat:end--> A deprecation calendar can
cover the other 1.5% and nothing more - not through any fault of its own, but
because there is nothing to list. Everything else can only be caught by
watching the catalogue change, which is what this does.

## Why not just use a deprecation calendar

Because a calendar can only list what a vendor announced, and every tracker in
this space is built that way and says so. `aimodelwatch.dev` states plainly
that its data is "sourced from official deprecation pages". Those are good
services and they have a blind spot they cannot close by trying harder:

> **A model that is simply gone one morning was never on anybody's calendar,
> because nobody ever published a date for it.**

This checks against a catalogue that is diffed every single day. Of the model
removals recorded so far, **every one of them** vanished with no end-of-life
date ever published. Those are exactly the ones a calendar cannot warn you
about, and exactly the ones that take down a running product without notice.

## In CI

```yaml
- run: |
    curl -sO https://neosignal-ai.vercel.app/check.py
    python check.py . --quiet
```

Or drop this in as `.github/workflows/model-check.yml`. It runs on push and
once a day, because the interesting case is not "did this PR add a dead model"
- it is "did a model you shipped last month disappear overnight".

```yaml
name: model check

on:
  push:
  pull_request:
  schedule:
    - cron: "17 6 * * *"

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.x"
      - name: Check for models that are gone or shutting down
        run: |
          curl -sO https://neosignal-ai.vercel.app/check.py
          python check.py . --quiet
```

| exit | meaning |
|---|---|
| `0` | nothing you call is going away |
| `1` | something is gone, or shuts down inside 30 days |
| `2` | the check could not run - **never** reported as a pass |

That last row is deliberate. A checker that says "fine" when it could not
reach its data is worse than no checker.

## It reads both spellings

`openai/gpt-5.2-chat` is the OpenRouter form. If you call a vendor SDK
directly you write `gpt-5.2-chat`, and both are matched. A bare name resolves
only when it maps to exactly one model in the catalogue, so a suffix two
vendors share is skipped rather than guessed at.

## Where it looks

Source in most languages, plus the places a model id actually hides: **Jupyter
notebooks, Dockerfiles, Makefiles, Terraform, Gradle** and config of every
shape.

That list is not a guess. An earlier version filtered on file extension alone,
was pointed at a project holding a model id in a notebook, a Dockerfile, a
Terraform variable and a Makefile, and found **none of the four** - then
printed "either a clean bill or the wrong directory", which reads as a pass. A
missed model is worse than no tool, because the tool was trusted.

## It does not cry wolf

It never guesses what a model id looks like. Every candidate token is kept
only if it matches a real id, so `utils/helpers`, `read-timeout-30` and
`on-click-handler` all survive a scan untouched. A bare name must also be at
least six characters and contain a digit.

When a model is gone it names the nearest still-listed option from the same
vendor and model line - and when nothing qualifies it **says nothing at all**.
That silence is the feature. An earlier version of this rule offered a safety
classifier as the successor to a 550B flagship, and an image model as the
successor to a coding model. Substitutability is not in the data, so the tool
speaks only when the two ids visibly sit in the same line.

## Before you run a script off the internet

Fair. Here is everything it does, and how to check rather than take my word.

**333 lines, one file, no dependencies.** Read it - it is shorter than the
README. It makes **two GET requests**, both to `neosignal-ai.vercel.app`, and
it opens your files **read-only**. There is no write, no `subprocess`, no
`eval`, no environment variable read, no telemetry, and nothing is sent
anywhere.

The copy served from the site and the copy in this repository are the **same
file**. You do not have to believe that either:

```
curl -s https://neosignal-ai.vercel.app/check.py | shasum -a 256
curl -s https://raw.githubusercontent.com/Yesol-Pilot/neosignal-check/main/neosignal_check.py | shasum -a 256
```

Two identical digests. If they ever differ, do not run it and please open an
issue.

## Tests

```
python test_neosignal_check.py
```

Standard library, no network, no test framework. 22 checks covering bare-name
resolution, the ambiguity guard, file discovery including Dockerfiles and
notebooks, the false-positive guard, verdicts, and the decision to stay silent
when no replacement qualifies.

Every case is a bug this tool actually shipped or nearly shipped on its first
day, written as the behaviour that was wrong at the time - a test that only
asserts what the code happens to do now protects nothing. They were checked by
deliberately reintroducing two of those bugs and confirming the suite goes red.

## Data

Both endpoints are free, keyless and CORS-open.

| endpoint | what it is |
|---|---|
| [`/api/models.json`](https://neosignal-ai.vercel.app/api/models.json) | every model, price, context window, end-of-life date |
| [`/api/changes.json`](https://neosignal-ai.vercel.app/api/changes.json) | what changed and what vanished, keyed by model id |

Full history of everything that disappeared:
[neosignal-ai.vercel.app/gone.html](https://neosignal-ai.vercel.app/gone.html)

## Caveat worth stating

This watches the OpenRouter catalogue. A model can leave an aggregator without
its vendor retiring it, so a removal here is evidence about that catalogue and
not proof the vendor killed the model. The tool says so in its own output, and
you should confirm with your provider before you migrate.

MIT licensed. Built by [Neo Genesis](https://neosignal-ai.vercel.app).

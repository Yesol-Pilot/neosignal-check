# neosignal-check

Find out which AI models your code calls have been **deprecated or removed** -
including the ones that were removed with no deprecation notice at all.

```
curl -sO https://neosignal-ai.vercel.app/check.py
python check.py .
```

<!--sample:start-->
```
3 models referenced in .

  ok     anthropic/claude-3-haiku     no change recorded
  GONE   openai/gpt-5.1-chat          GONE from the catalogue on 2026-08-01,
                                      with no end-of-life date ever published
         nearest still listed: openai/gpt-5.1 at $10.00 per million
         output, against the $10.00 it cost
         src/agent.ts
  SOON   openai/gpt-5.2-chat          shuts down 2026-08-10 - 7 days left
         src/agent.ts

2 need attention.
```
<!--sample:end-->

No key, no signup, no account, no dependencies. One stdlib Python file that
reads two public JSON endpoints.

The catalogue it checks against is OpenRouter's, diffed daily — but you do not
have to be an OpenRouter user. Three spellings of the same model resolve to one
entry, including the dated pin a vendor's own SDK takes. Details are in
[how a spelling is resolved](#how-a-spelling-is-resolved).

## What it has actually caught

Not a mock. Every row below left the catalogue on the date shown, and **not one
of them carried an end-of-life date in the catalogue beforehand** - so nothing
reading that catalogue could have warned you.

<!--evidence:start-->
| vanished | model | end-of-life date published? | nearest still listed |
|---|---|---|---|
| 2026-08-01 | `openai/gpt-5.1-chat` | **none, ever** | `openai/gpt-5.1` |
| 2026-08-01 | `mistralai/devstral-2512` | **none, ever** | _nothing qualifies_ |
| 2026-07-30 | `openai/o4-mini-deep-research` | **none, ever** | _nothing qualifies_ |
| 2026-07-30 | `openai/o3-deep-research` | **none, ever** | _nothing qualifies_ |
| 2026-07-30 | `openai/gpt-5-codex` | **none, ever** | `openai/gpt-5.1-codex` |

As of 2026-08-03.
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
<!--stat:end--> That is a statement about the
catalogue, not about vendors. Some vendors do publish retirement dates on their
own documentation and the catalogue simply does not carry them — see
[what this does not see](#what-this-does-not-see). Either way, anything reading
the catalogue is working from those few dates and nothing else.

## Why not just use a deprecation calendar

Because a calendar can only list what somebody announced, and every tracker in
this space is built that way and says so. `aimodelwatch.dev` states plainly
that its data is "sourced from official deprecation pages". Those are good
services and they have a blind spot they cannot close by trying harder:

> **A model that is simply gone one morning was never on anybody's calendar,
> because no date for it was ever published.**

This checks against a catalogue that is diffed every single day. Of the model
removals recorded so far, **every one of them** vanished with no end-of-life
date in the catalogue beforehand. Those are exactly the ones a calendar cannot
warn you about, and exactly the ones that take down a running product without
notice.

## What this does not see

The other direction, stated plainly because it is the honest half of the same
problem: **a vendor can publish a retirement date that the catalogue never
carries, and this will not see it either.**

Measured on 2026-08-03. Anthropic's own deprecation page lists a retirement
date of 2026-08-05 for `claude-opus-4.1`. The catalogue carries no date for it,
or for any of Anthropic's other sixteen models. Pointed at a repository calling
that model, this reported `no change recorded` and exited 0 — for a model with
two days left.

So the coverage is: **removals, seen the day they happen, from a daily diff**,
plus whatever dates the catalogue happens to carry. It is not a substitute for
your vendor's own deprecation page, and the tool no longer prints anything that
implies it is. Closing this properly means reading vendor documentation
directly, which is the next thing being built.

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

## How a spelling is resolved

| you wrote | resolves to |
|---|---|
| `openai/gpt-5.2-chat` | the catalogue id itself |
| `gpt-5.2-chat` | a bare name, as a vendor SDK takes it |
| `claude-haiku-4-5-20251001` | `anthropic/claude-haiku-4.5` — the vendor's dated pin |

All three reach the same entry, but each is tried in order and each can
decline:

1. the catalogue id, matched exactly;
2. a bare name, only where it maps to exactly one model — a suffix two vendors
   share is skipped rather than guessed at;
3. a vendor's own spelling, only after the first two find nothing. A dated pin
   sheds its date, a Bedrock id sheds its prefix and revision, and dots fold to
   dashes. Where the shortened form could mean more than one model it is
   dropped, not guessed.

The order matters: `gpt-4o` resolves on its own name at step 1, and shortening
it would collide with two dated snapshots of itself. Trying step 3 first would
turn a working answer into an ambiguous one.

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

<!--size:start-->
**463 lines, one file, no dependencies.**
<!--size:end--> Read it. It makes **two GET requests**, both to
`neosignal-ai.vercel.app`, and it opens your files **read-only**. There is no
write, no `subprocess`, no `eval`, no environment variable read, no telemetry,
and nothing is sent anywhere.

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

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

  ok     anthropic/claude-fable-5     no change recorded
  GONE   openai/gpt-5.1-chat          GONE from the catalogue on 2026-08-01,
                                      with no date in it beforehand
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
| vanished | model | date in the catalogue beforehand | nearest still listed |
|---|---|---|---|
| 2026-08-01 | `openai/gpt-5.1-chat` | **none** | `openai/gpt-5.1` |
| 2026-08-01 | `mistralai/devstral-2512` | **none** | _nothing qualifies_ |
| 2026-07-30 | `openai/o4-mini-deep-research` | **none** | _nothing qualifies_ |
| 2026-07-30 | `openai/o3-deep-research` | **none** | _nothing qualifies_ |
| 2026-07-30 | `openai/gpt-5-codex` | **none** | `openai/gpt-5.1-codex` |

As of 2026-08-03.
<!--evidence:end--> The live list is always at
[neosignal-ai.vercel.app/gone.html](https://neosignal-ai.vercel.app/gone.html),
and the raw records are in
[`/api/changes.json`](https://neosignal-ai.vercel.app/api/changes.json) if you
would rather check the claim than take it.

Where the last column says nothing qualifies, that is the tool declining to
guess. It names a replacement only when the two ids visibly sit in the same
vendor line.

## Retired by the vendor, still on sale

Neither source shows this alone. A calendar-based tracker reads the vendors'
deprecation pages and never diffs the catalogue, so it cannot tell you the entry
is still being served. A catalogue watcher diffs the listing and never reads the
vendor pages, so it cannot tell you the model is retired. This reads both, every
day, and the overlap is where these live.

<!--stale:start-->
**13 models are still listed after the vendor retired them.** The oldest by 689 days.

| model | vendor's retirement date | days still listed since |
|---|---|---|
| `openai/gpt-3.5-turbo-0613` | 2024-09-13 | **689** |
| `mistralai/mistral-large-2407` | 2025-03-30 | **491** |
| `google/gemini-2.5-pro-preview-05-06` | 2025-12-02 | **244** |
| `anthropic/claude-3-haiku` | 2026-04-20 | **105** |
| `google/gemini-3.1-flash-lite-preview` | 2026-05-25 | **70** |
| `anthropic/claude-opus-4` | 2026-06-15 | **49** |

and 7 more.

2 of these are still served on a platform whose own end-of-life is later - AWS Bedrock, in every current case - so for those the catalogue may be routing somewhere the model has not retired. The catalogue does not name the provider behind an entry, so that cannot be settled from it, and they are counted above rather than quietly dropped. The other 11 have no such route that we can see.

As of 2026-08-03.
<!--stale:end-->

Every row is checkable in one request from
[`/api/changes.json`](https://neosignal-ai.vercel.app/api/changes.json) — each
carries the vendor id the date was read from, so you can see which spelling the
claim rests on.

## Announced, then un-announced

<!--withdrawn:start-->
<!--withdrawn:end-->

## The number that explains why this exists

Measured against the live catalogue, and checkable from
[`/api/models.json`](https://neosignal-ai.vercel.app/api/models.json) in one
request:

<!--stat:start-->
| | |
|---|---|
| models whose catalogue entry carries an end-of-life date | **5 of 337** |
| vendors with a dated entry in the catalogue | **2 of 58** |

**98.5% of the catalogue carries no shutdown date at all.**
<!--stat:end--> That is a statement about the
catalogue, not about vendors. Vendors do publish retirement dates on their own
documentation; the catalogue simply does not carry them. Anything reading only
the catalogue is working from those few dates and nothing else, which is why
this reads
[the vendor pages as well](#it-reads-the-vendors-own-deprecation-page-too).

## Why not just use a deprecation calendar

A calendar lists what somebody announced. `aimodelwatch.dev`, read 2026-08-03,
describes its data as "Sourced from official docs, refreshed daily" across 204
models and 12 providers. That is a good service and the approach is sound for
everything a vendor writes down.

The gap is what nobody wrote down:

> **A model that is simply gone one morning, with nothing published anywhere
> about it, cannot be on a calendar - there was never a date to put there.**

This diffs the live catalogue every single day, so a disappearance is recorded
whether or not anyone announced it.

<!--calendar:start-->
Of the **5 removals** recorded so far, **2** had a date on the vendor's own deprecation page before they vanished and **3** did not. A calendar built on vendor docs catches the 2. Nothing but a daily diff of the catalogue catches the other 3 - the kind that takes a running product down without notice.

None of the 5 carried an end-of-life date in the **catalogue** beforehand - the field anything reading only the catalogue would have to rely on. Each removal in [`/api/changes.json`](https://neosignal-ai.vercel.app/api/changes.json) carries `vendor_announced`, and the announced ones carry the date and the vendor page it was read from, so this is checkable rather than assertable.
<!--calendar:end-->

## It reads the vendor's own deprecation page too

A catalogue diff catches removals. It cannot catch a retirement the vendor
announced but the catalogue never carried — and that is most of them.

Found on 2026-08-03 by checking this tool against Anthropic's own docs:
`claude-opus-4.1` retires 2026-08-05, the catalogue holds no date for it or any
of Anthropic's sixteen other models, and pointed at a repository calling it
this reported `no change recorded` and exited 0. Two days out.

So it reads vendors' deprecation pages directly and merges them into the same
record. Both sources, one answer:

<!--both:start-->
| | |
|---|---|
| models with a date in the catalogue | **5** |
| models with a date from their vendor | **23** |
<!--both:end-->

Every vendor-dated row carries the vendor id and page it came from, so any
warning traces back to a row you can read yourself. The build refuses to ship
if a claim's id does not match its source.

Where the two disagree, it says so rather than picking. A model the vendor
retired months ago while the catalogue still lists it gets exactly that
sentence, because which side is stale is the useful part.

### How much of the catalogue this actually covers

<!--coverage:start-->
**Vendor pages are read for 4 of the 58 vendors in the catalogue** - [anthropic](https://docs.claude.com/en/docs/about-claude/model-deprecations), [google](https://ai.google.dev/gemini-api/docs/deprecations), [mistralai](https://docs.mistral.ai/getting-started/models/models_overview/), [openai](https://platform.openai.com/docs/deprecations) - which is 125 of 337 models. For the other 212, the only lifecycle field is the catalogue's own, and that is empty for 98.5% of the catalogue.

So for **209 models there is no published retirement date anywhere this looks** - no vendor page read, nothing in the catalogue entry. That is the gap, stated rather than implied: a silent removal is the only warning those models will ever give, which is why the daily diff is the part that matters. The vendor list above is in [`/api/changes.json`](https://neosignal-ai.vercel.app/api/changes.json) under `vendor_pages_read`, so it can be checked rather than taken.
<!--coverage:end-->

**What it still cannot do:** a vendor page listing only deprecations says
nothing about a model it omits. OpenAI's carries `gpt-5-2025-08-07` and no
`gpt-5`, so the August snapshot is retiring and the rolling alias is not — and
a date is never projected from one onto the other. Six such claims were dropped
rather than published; one of them would have read "gpt-5 retires 2026-12-11".

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
| `0` | nothing it checked has a change or a date against it |
| `1` | something is gone, or shuts down inside 30 days |
| `2` | the check could not run - **never** reported as a pass |

Two deliberate wordings there. `2` is never a pass, because a checker that says
"fine" when it could not reach its data is worse than no checker. And `0` says
what was checked rather than that you are safe — it used to print "nothing you
call is going away", which is a claim about everything, and it made that claim
about a model with two days left.

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
**712 lines, one file, no dependencies.**
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

## Caveats worth stating

Two sources, and they can prove different things.

**A removal is evidence about the catalogue, not proof the vendor killed the
model.** A model can leave an aggregator while the vendor still serves it. The
tool words its own output that way — "gone from the catalogue, with no date in
it beforehand" — and you should confirm with your provider before you migrate.

**A retirement date is the vendor's own statement, which is stronger — but our
copy of it has an age.** The pages are read daily; if one breaks, the last good
read keeps being served rather than the claim disappearing, and the tool
appends how old the reading is once it passes a week. A date that has not been
re-read in a month is still probably right, and you should still check it.

MIT licensed. Built by [Neo Genesis](https://neosignal-ai.vercel.app).

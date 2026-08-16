# neosignal-check

Find out which AI models your code calls are **gone or shutting down** -
including the ones that vanished from the catalogue with **no date in it
beforehand**, and the ones a vendor retired while the catalogue kept selling
them.

```
curl -sO https://neosignal-ai.vercel.app/check.py
python check.py .
```

<!--sample:start-->
```
3 models referenced in .

  ok     anthropic/claude-fable-5     no change recorded
  GONE   inclusionai/ling-3.0-tiny:fr GONE from the catalogue on 2026-08-14,
                                      with no date in it beforehand
         src/agent.ts
  SOON   z-ai/glm-4.5                 shuts down 2026-12-31 - 139 days left
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

Route prefixes work too, so LiteLLM and anything shaped like it are already
covered — `azure/gpt-4o`, `bedrock/anthropic.claude-3-haiku-20240307-v1:0`,
`vertex_ai/gemini-2.5-pro` and
`together_ai/meta-llama/llama-3.3-70b-instruct` all land on the right entry.
And if you call through Bedrock, the spelling is what tells this tool that
**your** deadline is Bedrock's rather than the vendor's — those are months
apart on some models.

**HuggingFace repository ids resolve as well** — `Qwen/Qwen3-30B-A3B-Instruct-2507`,
`deepseek-ai/DeepSeek-R1`, `meta-llama/Llama-3.3-70B-Instruct`,
`MiniMaxAI/MiniMax-M2.5`. If your model name came out of `transformers`, you do
not have to rewrite it.

## What it has actually caught

Not a mock. Every row below left the catalogue on the date shown, and **not one
of them carried an end-of-life date in the catalogue beforehand** - so nothing
reading that catalogue could have warned you.

<!--evidence:start-->
| vanished | model | date in the catalogue beforehand | nearest still listed |
|---|---|---|---|
| 2026-08-14 | `inclusionai/ling-3.0-tiny:free` | **none** | _nothing qualifies_ |
| 2026-08-13 | `openai/gpt-5.3-chat` | **none** | `openai/gpt-5.4` |
| 2026-08-06 | `inclusionai/ling-3.0-flash:free` | **none** | _nothing qualifies_ |
| 2026-08-01 | `openai/gpt-5.1-chat` | **none** | `openai/gpt-5.1` |
| 2026-08-01 | `mistralai/devstral-2512` | **none** | _nothing qualifies_ |
| 2026-07-30 | `openai/o4-mini-deep-research` | **none** | _nothing qualifies_ |
| 2026-07-30 | `openai/o3-deep-research` | **none** | _nothing qualifies_ |
| 2026-07-30 | `openai/gpt-5-codex` | **none** | `openai/gpt-5.1-codex` |

As of 2026-08-14.
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
**14 models are still listed after the vendor retired them.** The oldest by 700 days.

| model | vendor's retirement date | days still listed since |
|---|---|---|
| `openai/gpt-3.5-turbo-0613` | 2024-09-13 | **700** |
| `mistralai/mistral-large-2407` | 2025-03-30 | **502** |
| `google/gemini-2.5-pro-preview-05-06` | 2025-12-02 | **255** |
| `anthropic/claude-3-haiku` | 2026-04-20 | **116** |
| `google/gemini-3.1-flash-lite-preview` | 2026-05-25 | **81** |
| `anthropic/claude-opus-4` | 2026-06-15 | **60** |

and 8 more.

3 of these are still served on a platform whose own end-of-life is later - AWS Bedrock, in every current case - so for those the catalogue may be routing somewhere the model has not retired. The catalogue does not name the provider behind an entry, so that cannot be settled from it, and they are counted above rather than quietly dropped. The other 11 have no such route that we can see.

As of 2026-08-14.
<!--stale:end-->

Every row is checkable in one request from
[`/api/changes.json`](https://neosignal-ai.vercel.app/api/changes.json) — each
carries the vendor id the date was read from, so you can see which spelling the
claim rests on.

## Announced, then un-announced

<!--withdrawn:start-->
**3 retirement dates have been withdrawn** - published by the vendor, then dropped from its page while the model stayed listed and callable.

| model | date it used to carry | noticed |
|---|---|---|
| `google/gemini-2.5-pro` | 2026-10-16 | 2026-08-03 |
| `google/gemini-2.5-flash-lite` | 2026-10-16 | 2026-08-03 |
| `google/gemini-2.5-flash` | 2026-10-16 | 2026-08-03 |


A deprecation calendar cannot show you this: it renders the vendor's page as it reads today, and today is the day that page stopped saying so. Also in [`/api/changes.json`](https://neosignal-ai.vercel.app/api/changes.json) under `vendor_date_withdrawn`.
<!--withdrawn:end-->

## The number that explains why this exists

Measured against the live catalogue, and checkable from
[`/api/models.json`](https://neosignal-ai.vercel.app/api/models.json) in one
request:

<!--stat:start-->
| | |
|---|---|
| models whose catalogue entry carries an end-of-life date | **3 of 411** |
| vendors with a dated entry in the catalogue | **1 of 59** |

**99.3% of the catalogue carries no shutdown date at all.**
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
Of the **8 removals** recorded so far, **2** had a date on the vendor's own deprecation page before they vanished and **6** did not. A calendar built on vendor docs catches the 2. Nothing but a daily diff of the catalogue catches the other 6 - the kind that takes a running product down without notice.

None of the 8 carried an end-of-life date in the **catalogue** beforehand - the field anything reading only the catalogue would have to rely on. Each removal in [`/api/changes.json`](https://neosignal-ai.vercel.app/api/changes.json) carries `vendor_announced`, and the announced ones carry the date and the vendor page it was read from, so this is checkable rather than assertable.
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
| models with a date in the catalogue | **3** |
| models with a date from their vendor | **20** |
<!--both:end-->

Every vendor-dated row carries the vendor id and page it came from, so any
warning traces back to a row you can read yourself. The build refuses to ship
if a claim's id does not match its source.

Where the two disagree, it says so rather than picking. A model the vendor
retired months ago while the catalogue still lists it gets exactly that
sentence, because which side is stale is the useful part.

### How much of the catalogue this actually covers

<!--coverage:start-->
**Vendor pages are read for 4 of the 59 vendors in the catalogue** - [anthropic](https://docs.claude.com/en/docs/about-claude/model-deprecations), [google](https://ai.google.dev/gemini-api/docs/deprecations), [mistralai](https://docs.mistral.ai/getting-started/models/models_overview/), [openai](https://platform.openai.com/docs/deprecations) - which is 181 of 411 models. For the other 230, the only lifecycle field is the catalogue's own, and that is empty for 99.3% of the catalogue.

So for **227 models there is no published retirement date anywhere this looks** - no vendor page read, nothing in the catalogue entry. That is the gap, stated rather than implied: a silent removal is the only warning those models will ever give, which is why the daily diff is the part that matters. The vendor list above is in [`/api/changes.json`](https://neosignal-ai.vercel.app/api/changes.json) under `vendor_pages_read`, so it can be checked rather than taken.
<!--coverage:end-->

**What it still cannot do:** a vendor page listing only deprecations says
nothing about a model it omits. OpenAI's carries `gpt-5-2025-08-07` and no
`gpt-5`, so the August snapshot is retiring and the rolling alias is not — and
a date is never projected from one onto the other. Six such claims were dropped
rather than published; one of them would have read "gpt-5 retires 2026-12-11".

## Checking the same list again next month

A scan ends with a link:

```
Watch these: https://neosignal-ai.vercel.app/w/#anthropic/claude-3-opus,openai/gpt-4o
```

That page answers the same question for exactly those ids — which are
retired, which have a shutdown date, which are fine. The list is in the URL,
so there is no account, no signup and nothing stored: bookmark it, or send it
to whoever owns the deploy. You can also open
[`/w/`](https://neosignal-ai.vercel.app/w/) and paste ids in by hand.

It is the same data the tool uses, from
[`/api/watch.json`](https://neosignal-ai.vercel.app/api/watch.json) — free, no
key. If you would rather be told than go looking, every model in the
catalogue also has its own RSS feed.

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

### Check that the copy you downloaded is this one

The file served from the site and the file in this repository are the same
bytes. Two commands, no trust required:

```bash
curl -s https://neosignal-ai.vercel.app/check.py | shasum -a 256
curl -sL https://raw.githubusercontent.com/Yesol-Pilot/neosignal-check/main/neosignal_check.py | shasum -a 256
```

The build refuses to deploy when they differ - that check exists because they
did differ once, for one deploy, while this page said they could not.

### Pinning it

`curl`-ing the site gets whatever is current, which is what you want from a
warning tool and not what you want in a build you need to repeat. To pin:

```bash
curl -sLo check.py https://raw.githubusercontent.com/Yesol-Pilot/neosignal-check/v0.1.0/neosignal_check.py
python check.py . --quiet
```

`python check.py --version` prints it, and `--json` carries `tool_version`, so
a logged result says which copy produced it.

A tag is frozen and the site tracks `main`, so the two match on the day a tag
is cut and drift apart afterwards - that is what pinning is for, and the hash
check above compares the site against `main` rather than against a tag for
exactly that reason.

The data is always live either way. Pinning fixes the code that reads it, not
the catalogue it reads.

### What `--json` gives you

Generated by running the tool, so it cannot describe a shape it no longer has:

<!--jsonout:start-->
```json
{
  "action_required": 2,
  "models_referenced": 6,
  "results": [
    {
      "detail": "GONE from the catalogue on 2026-08-06, with no date in it beforehand",
      "files": [
        "src/llm.py"
      ],
      "level": "gone",
      "model": "inclusionai/ling-3.0-flash:free"
    },
    {
      "detail": "its vendor published 2026-10-16 and has since withdrawn it - there is no published date now",
      "files": [
        "src/llm.py"
      ],
      "level": "moved",
      "model": "google/gemini-2.5-pro",
      "withdrawn_date": "2026-10-16",
      "withdrawn_noticed": "2026-08-03"
    },
    {
      "detail": "no change recorded",
      "files": [
        "src/llm.py"
      ],
      "level": "ok",
      "model": "anthracite-org/magnum-v4-72b"
    },
    {
      "detail": "its vendor retired this on 2026-04-20 - the catalogue still lists it",
      "files": [
        "src/llm.py"
      ],
      "level": "soon",
      "model": "anthropic/claude-3-haiku",
      "replacement": {
        "kind": "vendor_stated",
        "model": "claude-haiku-4-5-20251001"
      }
    }
  ],
  "scanned": ".",
  "tool_version": "2026.8.6.1"
}
```

`level` is one of `gone`, `soon`, `moved`, `ok`. Exit code 1 when anything is `gone` or `soon`, 2 when it could not reach the data - never a silent pass. The extra keys appear only when they apply: `replacement` on a removal, `platform` and `vendor_end_of_life` when your spelling names a platform, `withdrawn_date` when a vendor published a date and took it back.
<!--jsonout:end-->

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
   share is skipped rather than guessed at. Case is folded here, so `GPT-4o`,
   `gpt-4o` and `GPT-4O` are one model. That was not true until 2026-08-04:
   this step matched case exactly while step 3 folded it, so an uppercase
   spelling worked or did not depending on which step a model happened to be
   reachable by, and `GPT-4o` was reachable by neither;
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
least five characters and contain a digit.

That is easy to claim, so here is the measurement. On 2026-08-04, every
candidate token from four large unrelated repository trees — **610,499 unique
tokens**, restricted to the file types this tool actually reads — was resolved
through its own matching logic. Everything that came back was a real model
reference. **Zero false positives.**

Two of those trees are the Google Cloud SDK and a mirror of external
repositories, so most of that corpus is code with no connection to AI at all.

Here are the strings that got closest — every hit shaped like `vendor/name`
that was **not** a model, kept as a test case:

| in the wild | what it actually is |
|---|---|
| `@openai/codex` | an npm scoped package |
| `openai/codex#22004` | a GitHub issue reference |
| `#include "google/protobuf/util/json_util.h"` | a C++ include path |
| `import "google/protobuf/empty.proto";` | a protobuf import |
| `https://github.com/google/googletest/` | a repository URL |

None of them is reported, and
[the tests](https://github.com/Yesol-Pilot/neosignal-check/blob/main/test_neosignal_check.py) fail if that ever changes — together with
a real id in the same directory, so the tests cannot pass by finding nothing.

Running it over other people's code has found two cases where it *did* cry
wolf, both on 2026-08-04, both fixed the same day and pinned by tests:

- The catalogue sells models literally named `auto` and `free`. Spelling
  resolution keeps only the last path segment, so `billing/free` and
  `apis/edgecontainer/v1/auto` were reported as model references.
- `sha512-KhYd2Hjt/O1` — an npm integrity hash — resolved to `openai/o1` on its
  last two characters. Base64 contains slashes, so the tail of a hash reads as
  a path segment, and **every JavaScript repository ships a lockfile full of
  them.**

If you find another,
[open an issue](https://github.com/Yesol-Pilot/neosignal-check/issues) — a
false positive is treated as the most serious kind of bug this tool can have,
because a missed model is a disappointment and an invented one is a reason to
stop reading the output.

When a model is gone it names the nearest still-listed option from the same
vendor and model line - and when nothing qualifies it **says nothing at all**.
That silence is the feature. An earlier version of this rule offered a safety
classifier as the successor to a 550B flagship, and an image model as the
successor to a coding model. Substitutability is not in the data, so the tool
speaks only when the two ids visibly sit in the same line.

## Before you run a script off the internet

Fair. Here is everything it does, and how to check rather than take my word.

<!--size:start-->
**1150 lines, one file, no dependencies.**
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

**The catalogue diff cannot reach back before its first snapshot, so old code
depends on the vendor pages instead.** The first snapshot here is dated
2026-07-29. A model that left the catalogue before that was never observed
leaving, and for a few hours on 2026-08-04 this tool said "no change recorded"
about `claude-3-opus`, `claude-3-5-sonnet-20241022` and `gemini-2.0-flash` —
all three still referenced in real code, all three long retired.

That gap is now covered from the other side:

<!--delisted:start-->
**172 models that their vendor has retired and the catalogue no longer lists** are read from the vendors' own deprecation pages and reported with the vendor's date, the oldest retired on 2023-03-23. They are in [`/api/changes.json`](https://neosignal-ai.vercel.app/api/changes.json) under `retired_and_delisted`, and on [the going-away page](https://neosignal-ai.vercel.app/gone.html). Vendors covered: anthropic, google, mistralai, openai.
<!--delisted:end-->

What that does **not** cover: four vendors publish a deprecation page we read —
Anthropic, OpenAI, Google and Mistral — against 58 vendors in the catalogue. For
the other 54, a removal older than 2026-07-29 is still invisible, and "no change
recorded" there means *not seen*, not *fine*.

MIT licensed. Built by [Neo Genesis](https://neosignal-ai.vercel.app).

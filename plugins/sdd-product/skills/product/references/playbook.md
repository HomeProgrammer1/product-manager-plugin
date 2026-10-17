# Playbook: which pm-skills to run, when and why

Skill names are fully qualified: `<plugin>:<skill>`. Invoke them with the Skill tool. Prefer **skills** (frameworks) over pm-skills **commands** (`/discover`, `/strategy` …): commands are interactive multi-checkpoint workflows written for a human at the keyboard. Use a command only when the user asks for it by name.

Legend: **Q** quick · **S** standard · **D** deep. A step marked S runs at standard and deep depth.

## Route `validate` (new idea → GO / PIVOT / KILL)

| # | Depth | Step | Skill | Feeds |
|---|---|---|---|---|
| 1 | Q | Who has the problem | `pm-market-research:market-segments` | brief, `reach` |
| 2 | Q | Value proposition (JTBD) | `pm-product-strategy:value-proposition` | `problem`, `differentiation` |
| 3 | Q | Competitors (with researcher evidence) | `pm-market-research:competitor-analysis` | `competitors`, `features`, `positioning`, `competition` |
| 4 | S | Market size (with researcher evidence) | `pm-market-research:market-sizing` | `market`, `market` score |
| 5 | S | Risky assumptions (8 categories) | `pm-product-discovery:identify-assumptions-new` | `assumptions` |
| 6 | S | Prioritise: impact × uncertainty | `pm-product-discovery:prioritize-assumptions` | `assumptions` impact and uncertainty |
| 7 | S | Lean canvas | `pm-product-strategy:lean-canvas` | report, `wtp`, `feasibility` |
| 8 | S | Experiments for the test-first quadrant | `pm-product-discovery:brainstorm-experiments-new` | `experiments` |
| 9 | D | Monetisation options | `pm-product-strategy:monetization-strategy` | `wtp`, pricing |
| 10 | D | Pricing against rivals | `pm-product-strategy:pricing-strategy` | `competitors[].price` (you) |
| 11 | D | Beachhead segment | `pm-go-to-market:beachhead-segment` | `reach` |
| 12 | D | Five forces | `pm-product-strategy:porters-five-forces` | `competition` |
| 13 | D | Red-team framework on the strategy | `pm-execution:strategy-red-team` | report "Against" |
| 14 | S | Independent skeptic (agent, fresh context) | `sdd-product:skeptic` | `red_team` challenges |

At quick depth, use steps 1–3, the scorecard and the skeptic. Every dimension that no step touched is `assumed`, and the script caps it at 3.

Steps 3 and 4 get the researchers' verified evidence. Their skills normally search the web themselves; the orchestrator tells them not to, so you pay for each search once.

## Route `competition`

`pm-market-research:competitor-analysis` → (S) `pm-marketing-growth:positioning-ideas` → (D) `pm-go-to-market:competitive-battlecard` for the single most dangerous rival. Charts: features, positioning, pricing.

## Route `market`

`pm-market-research:market-sizing` → (S) `pm-market-research:market-segments` → (D) `pm-product-strategy:pestle-analysis`. Charts: market, trend.

## Route `business`

`pm-product-strategy:lean-canvas` → `pm-product-strategy:monetization-strategy` → (S) `pm-product-strategy:pricing-strategy` → (D) `pm-product-strategy:business-model`. Charts: pricing, scorecard (`wtp`, `feasibility` only if no full validation exists).

## Route `strategy`

`pm-product-strategy:product-vision` → `pm-product-strategy:product-strategy` (or `startup-canvas` for a pre-revenue idea) → (S) `pm-product-strategy:swot-analysis` → (D) `pm-product-strategy:ansoff-matrix`. Charts: positioning.

## Route `launch`

`pm-go-to-market:ideal-customer-profile` → `pm-go-to-market:beachhead-segment` → `pm-go-to-market:gtm-strategy` → (S) `pm-go-to-market:growth-loops` → (S) `pm-marketing-growth:north-star-metric` → (D) `pm-go-to-market:gtm-motions`. Charts: experiments (launch tests as experiments).

## Route `build`

`pm-execution:create-prd` → `pm-execution:prioritization-frameworks` (RICE on the MVP scope) → (S) `pm-execution:user-stories` → (S) `pm-execution:pre-mortem`. With `sdd-kit` installed, offer to hand the first story to `/sdd-kit:sdd`.

## Reduced mode (pm-skills not installed)

Apply the same frameworks by name from your own knowledge: segments, JTBD value proposition, competitor matrix, TAM/SAM/SOM, assumption mapping, lean canvas and pretotype experiments. Keep each one short. Label each such section `(without pm-skills)` so the user knows it is shallower.

## Next (offer after a route finishes)

| After | Offer |
|---|---|
| validate → GO | write the PRD for the MVP (`build`); plan the launch (`launch`); with sdd-kit, start the first feature |
| validate → PIVOT | rerun `validate` on the strongest alternative segment or positioning gap the report names |
| validate → KILL | name what evidence would reverse the verdict; run the cheapest experiment anyway if the founder still believes |
| validate → UNPROVEN | run the first experiment, put its notes into `evidence/`, then `--resume <slug>`; more desk research will not move the verdict |
| competition | sharpen positioning (`strategy`); price against them (`business`) |
| market | full validation (`validate`) |
| business, strategy | validate the riskiest assumption they created |
| launch | define the metrics dashboard (`pm-product-discovery:metrics-dashboard`) |

Offer, in plain words, at most three next steps. Do not hard-reference pm-skills commands as if they were guaranteed to exist.

## Install

```text
/plugin marketplace add phuryn/pm-skills
/plugin install pm-product-discovery@pm-skills
/plugin install pm-product-strategy@pm-skills
/plugin install pm-market-research@pm-skills
/plugin install pm-go-to-market@pm-skills
/plugin install pm-marketing-growth@pm-skills
/plugin install pm-execution@pm-skills
```

The orchestrator needs these six. `pm-data-analytics`, `pm-toolkit` and `pm-ai-shipping` are not used.

# Chart style for product validation

A product chart exists so the founder can say "yes, I see where this idea stands" in under a minute, and so a sceptic can see which numbers are facts and which are guesses.

## 1. One chart, one question

| Chart | Question it answers | Data |
|---|---|---|
| market | How big is the prize, and how much of it can we really reach? | `market.tam/sam/som` |
| trend | Is the market growing or shrinking? | `market.projection` |
| pricing | Where does our price sit against what buyers pay today? | `competitors[].price` |
| features | Where are we equal, better or missing? | `features`, `competitors[].features` |
| positioning | Is there an empty spot worth owning? | `positioning`, `competitors[].x/y` |
| assumptions | What could kill the idea, and what do we test first? | `assumptions` |
| scorecard | Go, pivot or kill, and how sure are we? | `scorecard` |
| experiments | What do we do in the next weeks, and what counts as success? | `experiments` |

A chart whose data is missing is skipped, not faked.

## 2. Budgets the renderer enforces

| | Comfortable | Hard limit |
|---|---|---|
| Products on matrix/positioning/pricing (you included) | 6 | 8 (error above) |
| Features in the matrix | 8 | 12 (error above) |
| Assumptions on the map | 8 | 12 (warning above) |
| Accent elements | your product only | — |

Choose rivals the buyer would really compare: direct rivals, the best indirect one, and "doing it by hand" (spreadsheet, chat, agency) when that is what people do today.

## 3. Colour and marks

- Your product is the accent; everyone else is one series colour. Colour follows the entity, never the rank.
- Feature cells use shape as well as colour (filled, half, ring, "?"), so they read in grayscale.
- The critical colour is reserved for a red-flag score (below 2), always with "!" and the words "red flag".
- Thin bars with 4 px rounded ends, hairline solid grid, one axis per chart, no dual axes, no pies.
- Every mark has a tooltip (`<title>`); the dashboard has a data table under each chart. SVGs carry `role="img"`, a title and a description, and switch to a dark palette with the system theme.

## 4. Positioning axes

Pick two axes buyers actually trade off (price vs depth, setup time vs power, self-serve vs managed). Avoid "quality" and "innovation": everyone rates themselves high on those. Score 0–10 from public evidence (pricing pages, docs, reviews), and put the reason in the report table.

## 5. Evidence levels and caps

| Level after `verify` | Meaning | Confidence weight | Highest score it supports |
|---|---|---|---|
| tested | quote found in a file the founder gave | 100% | 5 |
| verified | quote found on the public page | 80% | 5 |
| proxy | verified, but about another segment or geography (`direct: false`) | 50% | 4 |
| resolved | page opened, quote not found (or the quote is a fragment) | 50% | 4 |
| estimated | arithmetic shown in the report | 40% | 4 |
| unverified | claims a source nobody could confirm | 20% | 3 |
| assumed | a guess | 10% | 3 |

The scorecard shows the counted score as the bar and the claimed score as an outline behind it, plus the tag `claimed→counted · evidence`. The verdict line names the profile and warns when the verdict is **fragile**, meaning that ±0.5 on one dimension would flip it. A GO with low confidence means "worth testing", not "build it". UNPROVEN replaces KILL when nothing verified speaks against the idea, only the lack of evidence. Under the verdict line the chart shows what share of the score rests on the founder's data, on verified sources about this segment, on indirect sources and on guesses.

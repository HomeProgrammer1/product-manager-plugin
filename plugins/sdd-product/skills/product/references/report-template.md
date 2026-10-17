# Templates

## Brief (`product/<slug>/brief.md`)

```markdown
# <title>: brief
- **Idea:** <one sentence>
- **Who:** <segment> (confirmed | assumed)
- **Problem / job:** <in the user's words> (confirmed | assumed)
- **Where:** <countries, language> (confirmed | assumed)
- **Money:** <first guess at model and price> (confirmed | assumed)
- **Founder goal:** <side income | bootstrapped | venture; time; budget> (confirmed | assumed)
- **Route / depth:** <validate / standard>
- **Toolset:** pm-skills <plugins found | not installed>; web <yes | no>
```

## Report (`product/<slug>/report.md`)

```markdown
# <title>
<date> · route <route> · depth <depth> · pm-skills <yes|reduced mode>

## Verdict: <GO | PIVOT | KILL>, <score>/5, confidence <low|medium|high>
![Scorecard](charts/scorecard.svg)

**Why**
1. <reason with evidence level and source ids>
2. …
3. …

Profile <side|bootstrapped|venture> · sources verified <n>/<m> · capped by evidence: <dims or none> · challenged by the skeptic: <dims or none> · fragile: <dims or no>

**What would change the verdict:** <the one or two facts that would flip it, and which evidence level they need>

## Questions only you can answer
<questions from pm-skills or the skeptic about the founder's own facts; each one keeps a dimension at "assumed" until answered>

## Riskiest assumptions and the first experiments
![Assumptions](charts/assumptions.svg)
| Assumption | Experiment | Success if | Weeks |
|---|---|---|---|
![Experiments](charts/experiments.svg)

## Market
![Market](charts/market.svg)
<TAM/SAM/SOM with formulas for estimated values; growth chart if present>

## Competition
![Features](charts/features.svg)
![Positioning](charts/positioning.svg)
![Pricing](charts/pricing.svg)
<table: rival, type, price, why they win, where they are weak, sources>
<how each positioning score was decided, one line per rival>

## Customer and value
<segments, JTBD value proposition, lean canvas: compact>

## Against (independent skeptic)
<its strongest case against; each challenge with accepted or rebutted, and the verified source behind any rebuttal>

## Gaps
<what was not found, warnings left from the chart check, assumptions not yet tested>

## Sources
<S1 … with URL and access date>
```

Leave out any section whose route did not produce it. Do not pad.

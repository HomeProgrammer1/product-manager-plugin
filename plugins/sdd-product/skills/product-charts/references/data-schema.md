# data.json schema

One file per idea: `product/<slug>/data.json`. Every section is optional. A chart is drawn only when its section is present. A full example is in `../examples/example.data.json`.

```jsonc
{
  "meta": {
    "title": "Booking for small beauty salons",   // required
    "idea": "One sentence: who, what, why now",
    "slug": "salon-booking",
    "date": "2026-10-16",
    "language": "en",            // en | uk (chart chrome words)
    "currency": "USD",           // USD EUR GBP UAH PLN JPY, or any ISO code
    "price_unit": "seat",        // user | seat | ... (pricing chart subtitle)
    "illustrative": false,       // true only for examples and demos
    "steps": [                   // one entry per route step, written by the orchestrator
      { "n": 4, "skill": "pm-market-research:market-sizing", "mode": "skill" },        // skill | reduced | skipped
      { "n": 9, "skill": "pm-product-strategy:monetization-strategy", "mode": "skipped", "reason": "deep only" }
    ]
  },
  "sources": [
    { "id": "S1", "title": "…", "url": "https://…", "publisher": "…", "accessed": "2026-10-16", "data_year": 2025,
      "quotes": ["the whole sentence from the page that says the number and what it counts"] },
    { "id": "S4", "title": "Interviews with 5 owners (founder's notes)", "path": "evidence/interviews.md",
      "quotes": ["4 of 5 keep bookings by hand"] }
    // "verification" is written by `product_charts.py verify` only, never by hand
  ],
  "market": {
    "unit": "USD per year, Ukraine and Poland",
    "tam": { "value": 180000000, "basis": "sourced", "sources": ["S1"], "label": "what is counted" },
    "sam": { "value": 42000000,  "basis": "estimated", "label": "…",
             "inputs": [                                   // factors that multiply to value (±2%)
               { "label": "salons with 1-5 staff", "value": 38000, "basis": "sourced", "sources": ["S1"] },
               { "label": "already book in messengers", "value": 0.4, "basis": "assumed" },
               { "label": "yearly price", "value": 2763, "basis": "estimated" } ] },
    "som": { "value": 1300000,   "basis": "estimated", "label": "…" },
    "projection_metric": "sam",  // which value the trend chart shows (default tam)
    "projection": [ { "year": 2026, "sam": 42000000 }, { "year": 2027, "sam": 47000000, "projected": true } ]
  },
  "features": [ { "id": "f1", "label": "Booking inside the messenger" } ],
  "positioning": {
    "x": { "label": "Setup effort", "low": "weeks", "high": "5 minutes" },
    "y": { "label": "Feature depth", "low": "booking only", "high": "full CRM" },
    "quadrants": ["top-left", "top-right", "bottom-left", "bottom-right"]
  },
  "competitors": [
    { "name": "Your product", "you": true, "x": 9, "y": 3.5,
      "price": { "value": 9, "period": "month", "basis": "assumed" },
      "features": { "f1": "full" } },
    { "name": "Rival", "url": "https://…", "x": 6, "y": 6,
      "price": { "value": 348, "period": "year", "sources": ["S2"], "note": "annual billing" },
      "features": { "f1": "partial" } }
  ],
  "assumptions": [
    { "id": "A1", "text": "Owners will pay $9/month", "category": "viability", "impact": 5, "uncertainty": 5 }
  ],
  "scorecard": {
    "profile": "bootstrapped",   // side | bootstrapped | venture: sets thresholds and the weight of market size
    "dimensions": [
      { "id": "problem", "label": "Problem severity", "score": 4,
        "evidence": "tested", "sources": ["S4"], "why": "one line a sceptic can check" },
      { "id": "wtp", "label": "Willingness to pay", "score": 3, "evidence": "sourced", "sources": ["S2"],
        "direct": false, "why": "rival prices, not this buyer paying" }      // false: the source is about another segment or geography
    ]
  },
  "red_team": [
    { "dimension": "wtp", "claimed": 3.5, "proposed": 2, "reason": "…", "would_restore": "…",
      "sources": ["S9"],            // counter-evidence the skeptic found; added to sources and verified
      "resolution": "accepted" }    // or "rebutted" + "rebuttal_sources": ["S7"] (must be verified)
  ],
  "experiments": [
    { "id": "E1", "assumption": "A1", "method": "Landing page with price", "start_week": 1, "weeks": 2,
      "success": "≥ 5% of visitors press Pay", "focal": true }
  ]
}
```

## Field rules

- `basis` / `evidence`: one of `tested`, `sourced`, `estimated`, `assumed`. `sourced` needs a cited source with a `url` or `path`, and `tested` needs a cited founder file (`path`). What a claim **counts as** is decided by `verify` (see `chart-style.md` §5), not by this label.
- `price.value` is a number per `period` (`month`, `year`, `one-time`) and `null` when the price is not public. Yearly prices are shown per month, and one-time and recurring prices cannot be mixed. A competitor price defaults to `sourced`, so cite it or set `"basis": "estimated"` or `"assumed"`.
- `features` states: `full`, `partial`, `none`, `unknown`. A missing cell counts as unknown.
- `x`, `y`: 0–10. `impact`, `uncertainty`: 1–5. Scores: 0–5. The seven standard dimensions have fixed weights. Custom `weight`, `go_threshold` and `kill_below` values are ignored, and `check` warns about them.
- Exactly one competitor has `"you": true`.
- `quotes`: whole sentences of at least five words that say both the number and what it counts. A fragment such as "70.89%" verifies nothing and counts as "page found, quote not".
- `market.*.inputs`: every estimated TAM, SAM or SOM lists its factors. `check` multiplies them, and lists any factor marked `assumed`, so the reader sees which part of a market size is a guess.
- `direct: false` on a dimension whose sources describe another segment, market or geography (EU-wide statistics for a Polish niche, a rival's price for this buyer's willingness to pay). It then counts as an indirect source: at most 4.
- `meta.steps`: `reduced` or `skipped` needs a `reason`. Saving time is not a reason at standard or deep depth.
- `data_year`: the year the figure describes. `check` flags figures more than three years older than `meta.date`.

## Standard scorecard dimensions

Use these ids so verdicts are comparable between ideas. Add or drop one only with a reason in the report.

| id | label | weight | What a 4–5 looks like |
|---|---|---|---|
| problem | Problem severity | 2 | Frequent, costly, people already pay or hack around it |
| market | Market size | by profile | SAM large enough for the founder's goal (venture, SMB or side income) |
| competition | Open space | 1 | A clear gap on the positioning map that rivals cannot close quickly |
| differentiation | Differentiation | 1 | A reason to switch that buyers state in their own words |
| wtp | Willingness to pay | 2 | This segment already paid: a pre-sale, a deposit or a paid pilot (rival prices alone support at most 3) |
| reach | Reach | 1 | A cheap, repeatable channel to the first 100 customers |
| feasibility | Feasibility and fit | 1 | An MVP within the founder's time, money and skills |

Verdict (computed by the script from the **counted** scores):

| Profile | GO at | KILL below | Weight of `market` |
|---|---|---|---|
| side | 3.3 | 2.4 | 0.5 |
| bootstrapped | 3.5 | 2.5 | 1 |
| venture | 3.8 | 2.8 | 2 |

- Each score is first capped by its verified evidence, and then by red-team challenges that were not rebutted with verified evidence. A challenge backed by a verified source (`sources`) applies in full. A challenge without one ("the evidence is thin") lowers the score by at most 0.5, because thin evidence is already priced in by the cap.
- GO when the weighted score reaches the profile's threshold and no dimension is below 2.
- KILL when the score is below the KILL threshold, or two or more dimensions are below 2, **and** at least one low dimension rests on verified or tested evidence (or a verified challenge). Without evidence against the idea the verdict is **UNPROVEN**: not enough evidence either way.
- PIVOT otherwise.
- `grounded` in the verdict shows what share of the weighted score rests on the founder's data, on verified sources about this segment, on verified indirect sources, and on guesses.
- `fragile` lists the dimensions where ±0.5 flips the verdict.

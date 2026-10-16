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
    "illustrative": false        // true only for examples and demos
  },
  "sources": [
    { "id": "S1", "title": "…", "url": "https://…", "publisher": "…", "accessed": "2026-10-16",
      "quotes": ["exact words from the page that carry the fact"] },
    { "id": "S4", "title": "Interviews with 5 owners (founder's notes)", "path": "evidence/interviews.md",
      "quotes": ["4 of 5 keep bookings by hand"] }
    // "verification" is written by `product_charts.py verify` only, never by hand
  ],
  "market": {
    "unit": "USD per year, Ukraine and Poland",
    "tam": { "value": 180000000, "basis": "sourced", "sources": ["S1"], "label": "what is counted" },
    "sam": { "value": 42000000,  "basis": "estimated", "label": "…" },
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
        "evidence": "tested", "sources": ["S4"], "why": "one line a sceptic can check" }
    ]
  },
  "red_team": [
    { "dimension": "wtp", "claimed": 3.5, "proposed": 2, "reason": "…", "would_restore": "…",
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

- Each score is first capped by its verified evidence, and then by any red-team challenge that was not rebutted with verified evidence.
- GO when the weighted score reaches the profile's threshold and no dimension is below 2.
- KILL when the score is below the KILL threshold, or two or more dimensions are below 2.
- PIVOT otherwise.
- `fragile` lists the dimensions where ±0.5 flips the verdict.

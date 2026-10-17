# Evidence rules and the researcher return format

## What counts

| Level | Accept when | Example |
|---|---|---|
| tested | a file the **founder** gave you (interview notes, survey export, sales data), cited with `path` and a quote from it | "12 of 40 owners paid a $5 deposit" |
| sourced | a public page with URL, access date and the **exact words** that carry the fact (`quote`) | a competitor's pricing page; an industry report's stated figure |
| estimated | arithmetic over sourced inputs, with the formula in the report | 52,000 salons × 30% × $108/year |
| assumed | a reasonable default with nothing behind it yet | "owners will pay $9" |

- Prefer primary sources: pricing pages, official docs, regulator or statistics-office data, company filings. Use a press article or blog post only when no primary source exists, and say so.
- A market-size figure from a paywalled report teaser counts as sourced only when the number itself is visible on the page.
- Write down how fresh a source is. A figure older than three years can be used as an input but must be flagged.
- Two sources that disagree: keep both in `sources`, use the more conservative one, and note the spread.
- Bottom-up beats top-down: buyer count × share that has the problem × price × frequency. Show both when you have both.

## What the script checks

`product_charts.py verify` opens every source (URL or founder file) and looks for each `quote` in the page text. Case, quotation marks, spacing and thousands separators are ignored. The outcomes:

| Result | Counts as | Score cap |
|---|---|---|
| all quotes found in a founder file | tested | 5 |
| all quotes found on the page | verified source | 5 |
| page opened, quote missing (JS page, paywall, paraphrase) | resolved | 4 |
| page did not open, no URL, or never verified | unverified | 3 |

The record carries a signature made with a per-machine key in `~/.config/sdd-product/verify.key`. Editing a URL, a quote or a founder file afterwards invalidates it. The record also keeps about 250 characters around the match (`excerpt`), so a human or the skeptic can check it in seconds.

Quote the shortest exact phrase that contains the number or the fact: copy it, do not paraphrase. For a page rendered by JavaScript, look for the same fact on a static page (docs, a press release, a cached copy) before you accept `resolved`.

## Researcher brief (what the orchestrator sends)

```
QUESTION: competitors | market | channels
BRIEF: <who, what problem, where, business model, founder goal: 5 lines>
KNOWN: <competitors or figures the user already named>
LIMIT: at most <n> searches and <m> page fetches
```

## Researcher return format

The return is strict JSON inside one fenced block, then at most three lines of notes.

```json
{
  "question": "competitors",
  "sources": [{"id": "R1", "title": "…", "url": "https://…", "publisher": "…", "accessed": "YYYY-MM-DD",
               "quotes": ["exact words copied from the page that carry each fact used from it"]}],
  "competitors": [
    {"name": "…", "url": "https://…", "type": "direct|indirect|manual",
     "price": {"value": 15, "period": "month", "sources": ["R1"], "note": "entry paid plan"},
     "features": {"<feature label>": "full|partial|none|unknown"},
     "positioning_signals": ["self-serve, 5-minute setup (R1)"],
     "traction": "public signal with source id, or null"}
  ],
  "market": [
    {"metric": "number of salons in Poland", "value": 52000, "unit": "businesses", "year": 2025,
     "sources": ["R2"], "quote": "short quote that contains the number"}
  ],
  "not_found": ["what was searched and not found"]
}
```

The orchestrator renames source ids to the next free `S…` id when merging, deduplicates by URL, and turns feature labels into `features[]` ids.

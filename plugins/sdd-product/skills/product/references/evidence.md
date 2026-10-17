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
| quotes found, but about another segment or geography (`direct: false`) | indirect source | 4 |
| page opened, quote missing (JS page, paywall, paraphrase, PDF without pdftotext, fragment quote) | resolved | 4 |
| page did not open, no URL, or never verified | unverified | 3 |

The record carries a signature made with a per-machine key in `~/.config/sdd-product/verify.key`. Editing a URL, a quote or a founder file afterwards invalidates it. The record also keeps about 250 characters around the match (`excerpt`), so a human or the skeptic can check it in seconds.

Quote the **whole sentence** that contains the number and says what it counts, at least five words: copy it, do not paraphrase or translate. "70.89%" or "Poland (8.36%)" alone prove nothing about what was measured, so `verify` does not accept them. For a page rendered by JavaScript, look for the same fact on a static page (docs, a press release, a cached copy) before you accept `resolved`. PDF sources are read with `pdftotext` when it is installed; otherwise they count as `resolved`.

Record `data_year` for every figure: the year it describes, not the year the page was published.

**Direct or indirect.** A verified source still has to be about this buyer. EU-wide adoption statistics for a Polish niche, or a rival's price used as this buyer's willingness to pay, are indirect: mark the dimension `"direct": false`.

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
               "data_year": 2025,
               "quotes": ["the whole sentence copied from the page: number plus what it counts"]}],
  "competitors": [
    {"name": "…", "url": "https://…", "type": "direct|indirect|manual",
     "price": {"value": 15, "period": "month", "sources": ["R1"], "note": "entry paid plan"},
     "features": {"<feature label>": "full|partial|none|unknown"},
     "positioning_signals": ["self-serve, 5-minute setup (R1)"],
     "traction": "public signal with source id, or null"}
  ],
  "market": [
    {"metric": "number of salons in Poland", "value": 52000, "unit": "businesses", "year": 2025,
     "sources": ["R2"], "quote": "the whole sentence that contains the number"}
  ],
  "not_found": ["what was searched and not found"]
}
```

The orchestrator renames source ids to the next free `S…` id when merging, deduplicates by URL, and turns feature labels into `features[]` ids.

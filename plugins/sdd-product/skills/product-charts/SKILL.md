---
name: product-charts
description: Check and render the charts of a product validation folder (product/<slug>/data.json) into editorial SVG and a review dashboard - market size, trend, pricing, feature matrix, positioning map, assumption map, scorecard and experiment plan. Use after the sdd-product orchestrator writes or changes data.json, or when asked to redraw those charts. Not for code diagrams or free-form charts.
argument-hint: "<slug | path to data.json> [--check] [--tokens <design-tokens.json>]"
allowed-tools: Bash(python3 *), Read, Glob
---

# Product charts

Arguments: `$ARGUMENTS`

`data.json` is the **single source of truth**. Everything in `product/<slug>/charts/` is generated, stamped with the hash of the data it came from, and never edited by hand. To fix a chart, fix the data and rebuild.

## Steps

1. **Find the file.** A slug means `product/<slug>/data.json`, and a path means that file. If there is no data file, stop and report `NO_DATA`. The schema is in `${CLAUDE_SKILL_DIR}/references/data-schema.md`.
2. **Check first** (writes nothing):
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/product_charts.py" check product/<slug>/data.json
   ```
   - `error` lines (SOM larger than SAM, a "sourced" number with no source, more than 8 products or 12 features, a score outside 0–5, an experiment without a success criterion): fix `data.json` and check again.
   - `warn` lines (only an assumed TAM, many unknown cells, a test-first assumption with no experiment): fix them when the fix is cheap. Otherwise list them in the report under "Gaps".
3. **Build** when there are no errors (with `--check`, stop after step 2):
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/product_charts.py" build product/<slug>/data.json [--tokens <tokens.json>]
   ```
   Pass `--tokens` when the project's CLAUDE.md names a design-system tokens file. The same token names as sdd-diagrams work, plus `chart.series`.
4. **Look at the result.** Read at least `scorecard.svg` and `positioning.svg`. If a label collides or a chart is crowded, cut data (fewer products, shorter labels). Never hand-edit SVG.
5. **Report** in this shape:
   ```
   CHARTS: <n> rendered, skipped: <names>
   FILES: product/<slug>/charts/index.html
   VERDICT: <GO|PIVOT|KILL> <score>/5, confidence <low|medium|high>
   ISSUES: none | <warnings left and why>
   ```

## Rules

- Read `${CLAUDE_SKILL_DIR}/references/chart-style.md` before shaping data for a chart.
- The verdict is computed by the script from the scorecard, not chosen by the model. To change a verdict, change a score and its `why`, together with the evidence behind it.
- Charts never show a number without its evidence level (tested, sourced, estimated or assumed).
- Other chart and diagram tools can stay installed. This skill only writes `product/*/charts/`.

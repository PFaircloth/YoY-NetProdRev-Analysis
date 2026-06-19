# Backlog

## Phase 3 — Unified YoY + Forecast Dashboard

**Concept:** Combine the YoY-NetProdRev-Analysis and forecast-model pipelines 
into a single unified report showing the complete Jan 2025 – Dec 2026 picture.

**The complete story in one view:**
- Jan–May 2025 actuals (YoY baseline)
- Jan–May 2026 actuals (YoY current year)
- Jun–Dec 2026 forecast (forward-looking)
- Clear visual boundary between actuals and forecast

**Proposed unified views:**

### 1. Unified Office Heat Map
- Columns: Jan 25 Act | Feb 25 Act | ... | May 25 Act | Jan 26 Act | ... | May 26 Act | Jun 26 Fcst | ... | Dec 26 Fcst
- Color coding: actuals use YoY Δ Rev/Day heat scale, forecast uses Variance % heat scale
- Clear vertical divider between YoY actuals and forecast columns

### 2. Rev/Day Continuity Analysis
- Surface whether forecast assumptions are consistent with YoY performance trends
- If $/Visit is declining YoY, flag whether forecast accounts for continued pressure
- Compare YoY lever decomposition ($/Visit × Vis/DrDay × DrDays/Day) against forecast method assumptions

### 3. Provider Continuity
- Track same providers across both models
- YoY performance on left informs whether forecast method (T6M, T3M, T1M) is appropriate
- Highlight providers where YoY trend contradicts forecast method

### 4. New Patient Pipeline Connection
- NPs lost YoY is a leading indicator for future revenue
- Surface NP trend alongside forecast to show pipeline risk
- Flag offices where NP losses YoY suggest forecast may be overstated

### 5. Full Year Summary KPIs
- Total 2025 actuals (Jan–Dec 2025 when available)
- Total 2026 = Jan–May actuals + Jun–Dec forecast
- YoY full year variance
- Forecast confidence indicator based on method mix (T6M vs T1M vs FUTURE_START)

**Technical approach:**
- Single run.py entry point that reads from both project pipelines
- Or: shared data layer with two separate report generators feeding one HTML
- Recommend building as a new project: unified-revenue-dashboard/
- Both existing pipelines remain standalone and unchanged

**Dependencies:**
- YoY-NetProdRev-Analysis pipeline complete ✓
- forecast-model pipeline complete ✓
- Shared provider name normalization already in place ✓
- Working days config consistent across both models ✓

**Estimated complexity:** High — requires reconciling two separate data models, 
handling the actuals/forecast boundary, and building a new unified HTML template.
Recommend dedicated project sprint.

## Mix Shift (procedure-mix data layer) — known/intentional notes

- **`[Root Canal]` empty column is BY DESIGN — not a defect, do not re-investigate.**
  The DAX procedure-mix source (`data/X. DAX_ProcedureMix.xlsx`, sheet `Procedure_Mix`)
  ships `[Root Canal]` as a reserved-for-future-use column that is currently 100% empty.
  Root-canal activity is already captured under the Endo group via `[Molar Endo]` +
  `[Ant Bicuspid Endo]`, so **Endo is COMPLETE, not undercounting.** The group definition
  is `Endo = [Molar Endo] + [Ant Bicuspid Endo] + [Root Canal]`; the null-safe sum means
  `[Root Canal]` contributes 0 today and will auto-flow into Endo if/when the column is
  populated upstream — **no future code change needed.** Keep the column in the Endo
  definition as-is. The data-layer reconciliation intentionally surfaces it as a
  heads-up only; it must not be treated as an error or a STOP condition.

- **Negative 2026 production from departed providers — review REVENUE tabs (observation, not a task).**
  Departed providers with *negative* 2026 production (post-departure adjustments /
  write-offs, e.g. Liguori −$32,191, Hartmann −$57,535) still qualify into the rendered
  360 because the qualification key is `pk = max(np_2025, np_2026)` — their strong 2025
  carries them in. **Mix Shift (Tab 5) handles this cleanly**: it is visit-based, detects
  near-zero 2026 activity (<5% of 2025 visits, tunable `T5_INACTIVE_FRAC`), and renders an
  explicit factual label ("no 2026 activity" / "minimal 2026 activity (N visits)") instead
  of misleading per-100 rates. **But the negative 2026 production flows into the REVENUE
  tabs' deltas/totals** (Office Analysis, Provider Deep Dive, Data Summary) — worth a review
  of how those negatives render there (e.g. whether a −$57k "production" reads sensibly in
  YoY Δ and YTD gap). Observation only.

- **Consolidated lever view — operating-offices-only vs Other/wind-down split (not built).**
  The "MDP — Consolidated" company row (Office Analysis tab) ties to the KPI cards by
  consolidating 76 named **+ the "Other" rollup** (= the full $7.6M decline). But "Other"
  carries *negative* production (departed / wind-down accounting adjustments), which is a
  different KIND of cause than operating price/volume erosion. So the consolidated lever
  card's "Primary: ___" driver may be partly skewed by Other's negative adjustments rather
  than reflecting real operating performance. Consider a way to see **operating-offices-only
  vs Other/wind-down** in the consolidated lever view (e.g. a toggle or a second pinned row),
  so the company "primary lever" can be read as genuine price/volume movement vs. accounting
  cleanup. Observation/feature idea — don't build the split with the first tied-to-KPI row.

## Other Backlog Items

- ~~Partial month YTD support — config flag for Days Passed as denominator~~ **DONE**
  (commit b4e6cf0): month handling is fully elastic — active months derived from the
  data (year-intersection), all four tabs flex to N months, partial month flagged as
  "<Mon> (MTD)" via `config.MTD_MONTH`, June working-days added so Rev/Day is exact.
- **Load-time input validation** — the source export has repeatedly proven unstable;
  build a validation/normalization pass that fails loud (or auto-corrects + logs) on
  load instead of silently producing wrong numbers. Running evidence the export isn't
  trustworthy:
  - **ROW_CLASS casing drift** (fixed commit b02b0cb): June 2026 detail rows arrived as
    `"Detail"` instead of `"DETAIL"`; the case-sensitive filter silently dropped them, so
    provider-grain June rendered $0 in Data Summary while office totals (SUMMARY) looked
    fine. Now normalized via `.str.strip().str.upper()` in `load_source_data`. A validator
    should assert ROW_CLASS ∈ {SUMMARY, DETAIL} (post-normalize) and flag stray values.
  - **Duplicate SUMMARY rows** — office-level rows have appeared duplicated; validator
    should assert one SUMMARY row per office/month/year.
  - **July–Dec partial/inconsistent data** — later months arrive incomplete or only in
    one year; currently handled by the year-intersection month window, but a validator
    should surface per-month/per-year row-count gaps explicitly rather than letting them
    vanish silently.
- SharePoint/email distribution pipeline
- Azure Static Web Apps hosting
- Monthly automated refresh — drop in new source file, run one command
- `data/A...xlsx` is a tracked data file — reconsider whether source data belongs in
  version control; likely should be gitignored and kept out of the repo, with a
  documented load process instead.

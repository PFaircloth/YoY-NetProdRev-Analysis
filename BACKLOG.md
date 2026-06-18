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

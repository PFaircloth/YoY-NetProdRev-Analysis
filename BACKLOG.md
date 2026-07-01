# Backlog

## ⭐ CRITICAL (after Phase 2) — INTERPRETATION LAYER: guided $7.6M-drop diagnosis

**Priority:** critical / high-value — likely the highest-leverage remaining build. It turns
a collection of views into a guided *methodology*. **Do AFTER Phase 2** (realization view)
is complete, so it points at a finished view-set.

**Two presentations of one diagnosis — same workstream:**
- **(A) Decision Tree** = *how to investigate* (the branching elimination logic).
- **(B) Summary / Takeaways tab** = *what we found* (plain-language synthesis).

They are twins: same diagnosis, the tree teaches the path, the summary states the verdict.
Build together so they can't drift apart.

### (B) Summary / Takeaways tab — plain-language synthesis of the diagnosis
A standalone tab that states the conclusion in plain language: the two levers that moved,
each with a one-line "why" and a drill-link to the view that proves it, PLUS an explicit
**"NOT the cause:"** line (mix / intensity / pricing / capacity — what we ruled out). The
audience reads this first to get the answer; the tree and views are where they verify it.
- **CRITICAL — numbers MUST derive from the live data, not hardcoded sentences.** Every
  figure ($7.6M drop, $/Visit Δ, +2.1 pt realization, the "not the cause" magnitudes) must
  read from the pipeline/payload at build time, so it can never go stale-literal as months
  refresh. No baked-in prose numbers.
- Twin of the decision tree (tree = how to investigate, summary = what we found).

### (A) Decision Tree — guided investigation framework

**What:** A guide that hand-holds the audience through HOW to navigate the revenue-drop
investigation — externalizing the diagnostic *reasoning*, not just presenting views. Starts
at the **$7.6M YoY drop** and branches step-by-step; each node names the report view that
answers that question.

**Why:** We have the VIEWS (consolidated lever card, Mix Shift, Procs/Visit intensity,
realization diagnostic). What's missing is the connective REASONING — which question to ask
first, and what to do with each answer — which currently lives only in analysis sessions.
The tree externalizes it so the next person (or future-self) can run the diagnosis without
rediscovering the path.

**Shape (the elimination logic we actually used):**
- **Step 1** — decompose Rev/Day into levers (consolidated lever card): which lever moved?
  (Rev/Day = $/Visit × Visits/DrDay × DrDays/Day)
- **Branch A — Vis/DrDay:** volume vs intensity (Procs/Visit). If volume → where
  (hygiene/Other categories) → new-patient/recall → **demand/acquisition problem (front office)**.
- **Branch B — $/Visit:** billing-less vs collecting-less (gross/proc vs adjustment rate).
  Realization erosion (+2.1 pts company-wide, gross holding) → **revenue-cycle/payer problem**.

**Requirements / cautions:**
- Must map genuine **BRANCHES**, not retell our one path — handle cases where the answer
  differs (intensity DID drop, pricing WAS the issue, etc.). The value is in the branching,
  not the narration.
- **Navigation layer only** — routes to the views, does NOT reproduce/duplicate the data
  (avoid a parallel artifact that drifts out of sync).
- Start with a **STATIC decision-tree document** (format #1); assess whether an interactive
  guided version is worth building afterward.

## EXPORT SUB-PROJECT — Office-Lever Export for the "Office Brief Project"

**Status:** scoped, not yet built. **Trigger:** when the Office Brief Project is ready to
consume it (period to be confirmed there).

**Purpose:** Produce a parameterized per-office lever export that the new **Office Brief
Project** consumes as an input. This model **OWNS the export** (the lever logic lives here);
the Office Brief Project is the downstream **CONSUMER**.

**What to build:**
- A parameterized export function: `export_office_levers(start_period, end_period)` → clean
  per-office CSV.
- One row per office, across the **operating + wind-down + ramp** offices.
- Columns: office name, lifecycle class (operating / wind-down / ramp), and the **six
  levers** — $/visit, visits/dr-day, dr-days/day, net-prod-rev/day, total visits,
  new patients — computed **for the given period** using this model's existing (verified)
  lever logic.
- **PARAMETERIZED period (not hardcoded)** — the Office Brief Project's period is still being
  scoped; initial target is **trailing 12 complete months = June 2025 – May 2026** (fully
  within File A; all complete months, no MTD/partial). Build it to accept any `[start, end]`
  so future periods are a parameter change, not a rebuild.

**Key notes:**
- Lever values for **June 25 – May 26 will DIFFER** from this report's **Jan 25 – Jun 26**
  values (different period — expected, not a discrepancy).
- Only periods present in File A can be exported (currently **Jan 2025 onward**; reaching
  before Jan 2025 would require more history).
- **Format: CSV** (drag-and-drop friendly for the downstream model).
- **Architecture:** this model **PUBLISHES** the export; the Office Brief Project
  **SUBSCRIBES** — clean file-based handoff, no shared code, models stay independent.

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

- **Material contributors declined MORE than the company overall (observation, not a task).**
  The Mix Shift visits anchor is scoped to the rendered 360 material contributors and shows
  **216,107 → 188,400 visits (−12.8%)**. The all-provider company total (Office Analysis /
  consolidated population, which ties to the $7.6M) fell **247,561 → 221,488 (−10.5%)**. So
  the **core/material providers lost proportionally more volume than the company as a whole**
  — the visit decline is concentrated in material contributors, not the long tail. Each tab's
  anchor matches its own population by design (don't cross them); this gap is a real signal
  worth a look, not a reconciliation error. Observation only.

- **Mix source June 2025 is FULL-month, not truncated like File A — Volume uses Jan–May matched (presentation fix in place; source fix outstanding).**
  The DAX procedure-mix extract returns a **full** June 2025 (rendered-360 visits ≈ 36,707,
  like May) but a **partial** June 2026 MTD (≈ 21,748). File A (revenue tabs) truncates the
  prior-year June to the matched ~10.8-working-day window (≈ 24,665 vs 22,621), so the rest of
  the report is apples-to-apples; the **mix source is not**. Comparing full-June-2025 vs
  partial-June-2026 overstated the Mix decline (anchor was −12.8% Jan–Jun vs the true
  **−7.1% Jan–May matched**; company Filling went from a spurious −6.0% to a true +0.2%).
  **Presentation fix shipped:** Mix Shift Volume columns + visits anchor now use the **Jan–May
  matched window** (full months, both years) and show June separately as an MTD partial; per-100
  (Mix) stays Jan–Jun (window-invariant). **Outstanding:** the proper long-term fix is upstream —
  truncate June 2025 in the DAX extract to the matched MTD window so the full Jan–Jun can be
  compared. Until then, Jan–May-matched is the correct presentation. Each tab labels its own
  window explicitly; don't read Volume (Jan–May) and Mix (Jan–Jun) as the same period.

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

## Working days Jan–Jun — RESOLVED (equal both years; decline is all-rate)

**Jan–Jun working days are equal both years (111.4 = 111.4)**, so the −$8.05M half-year
decline is **entirely a rate story** — there is no working-day timing effect.

An earlier stale partial-June config value (`WORKING_DAYS[(6,·)] = 10.8`, the June-MTD figure)
produced totals of 103.6 / 102.6 and a **phantom −$0.75M "lost day"** — an artifact, not a
real calendar effect. **Resolved** by completing June to full-month values (18.6 / 19.6,
Tredence Company Summary Report) and setting `MTD_MONTH = None`; June is now complete across
every window (Rev/Day, realization, mix volume). The walk line is single-factor:
−$72,273/day × 111.4 working days ≈ −$8.05M.

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
  - **Mix source (DAX) emits MALFORMED count-column headers — ask data source to fix the
    export.** The procedure-mix extract (V/V2 re-pulls) exports the 14 bare COUNT measures
    with a trailing space and **no closing bracket** — `'[Crown '`, `'[Bone Graft '`, … —
    while every suffixed dollar column is properly bracketed (`[Crown Gross $]`, etc.). The
    clean codebase expects the proper `[Crown]` form (`mix_pipeline.PROC_GROUPS`), so the V2
    promotion required a one-time **header-normalization step** (rename the 14 bare counts
    `'[Crown ' → [Crown]` before writing canonical `data/X. DAX_ProcedureMix.xlsx`; dollar
    columns and keys left untouched). **Request to the data source:** fix the DAX export so
    future pulls emit clean bracketed count names — then this normalization step disappears
    and promotion is a straight file swap again (as the W promotion was). A load-time
    validator should also assert the count headers match the expected clean set and flag the
    malformed `'[Name '` form rather than silently failing `validate_columns`.
- SharePoint/email distribution pipeline
- Azure Static Web Apps hosting
- Monthly automated refresh — drop in new source file, run one command
- ~~`data/A...xlsx` is a tracked data file — reconsider whether source data belongs in
  version control~~ **DONE** (commit 1f7aa15): File A untracked via `git rm --cached`
  (kept on disk), now covered by the `data/*.xlsx` ignore rule so monthly refreshes stay
  out of git. Resolved the stale-committed-data problem (HEAD's File A was a pre-June-2026
  snapshot). `B.Provider_Map_Prod.xlsx` stays tracked (stable reference map).

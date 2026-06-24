# Procedure Mix — Adjustment Allocation Methodology

**Purpose:** correct how production adjustments (write-offs, contractual reductions) are
distributed across the 14 procedure types in the Procedure Mix extract, so each
procedure's **Net $** reflects the office/provider/month's *actual* adjustment rather than
a company-wide average. Hand-off companion to `ProcedureMix_Corrected_Allocation.dax`.

---

## 1. The problem with the current allocation

The current model allocates each procedure's adjustment using a **single company-wide
rate** (Σ all adjustments ÷ Σ all gross ≈ **−13.81%**), applied uniformly to every
procedure's gross. Verified against the extract: per-procedure `Adj $ = Gross $ × −0.138111`
for **100% of cells**, exactly.

Because the rate is global, it ignores that adjustment rates vary enormously by office:

| Office (example) | Actual adjustment rate | Flat rate applied |
|---|---|---|
| JR Dental | −52% | −13.8% |
| Metro OMS (oral surgery) | −46% | −13.8% |
| Davis Dental | ~0% | −13.8% |
| Mary Esther | +14% (net > gross) | −13.8% |

The flat method **nets out at the company level** (so the grand total looked correct) but
**misstates net at the office/procedure level by $36.4M in absolute terms** — overstating
net at high-write-off surgical/specialty offices and understating it elsewhere.

## 2. The correction — per-row proportional allocation

Allocate each **row's own** `[Total Adj]` in proportion to each procedure's share of that
**same row's** gross:

```
Procedure Adj $ = [Total Adj] × ( Procedure Gross $ / [Total Gross Prod] )
Procedure Net $ = Procedure Gross $ + Procedure Adj $
```

Because the 14 procedure gross values already sum to `[Total Gross Prod]` for every row,
the allocated adjustments sum back to `[Total Adj]` and the procedure net sums to
`[Total Net Prod]` — exactly, by construction. The DAX implements this by referencing the
`[Total Adj]` and `[Total Gross Prod]` measures **inside each row's context** rather than a
query-level VAR (which is what produced the flat rate).

## 3. Zero-gross rows

Some rows have adjustments but **no gross production** in the period (refunds / write-offs
of prior-period production). Proportional-by-gross is undefined there (0 ÷ 0), so:

- every procedure's `Adj $` and `Net $` is set to **0**, and
- the row's `[Total Adj]` is carried in a dedicated **`Unallocated Adj $`** measure.

This loses nothing: the company total reconciles as
`Σ(Procedure Net $) + Σ(Unallocated Adj $) = Σ(Total Net Prod)`.

**Context:** the unallocated amount is **−$1,616,575.35** across **3,780** zero-gross rows
(≈0.7% of company net). It is genuine prior-period adjustment with no current-period
procedure to attach to — surfaced explicitly rather than smeared onto procedures. If a
future refinement is wanted, the options are (a) leave as Unallocated (recommended —
transparent), (b) allocate against trailing-period gross, or (c) route to the Other bucket.

## 4. Validation results (File V2)

The corrected logic was applied to the full extract (13,565 rows, Jan 2025 – Jun 2026) and
exported as **File V2** (`V2. DAX_ProcedureMix_withDollars_andAdj_Corrected.xlsx`), keeping
all original columns and adding the corrected columns alongside. All checks **passed**:

| # | Check | Result |
|---|---|---|
| 1 | Σ procedure Gross $ = `[Total Gross Prod]` (every row) | ✅ max residual **$0.000000** |
| 2 | Σ procedure Net $ Corrected = `[Total Net Prod]` (8,584 production rows) | ✅ max residual **$0.000000** |
| 3 | Σ procedure Adj $ Corrected + `Unallocated Adj $` = `[Total Adj]` (every row) | ✅ max residual **$0.000000** |
| 4 | Company-wide net ties to **$216,099,290** | ✅ reconstructed **$216,099,290.48** (exact) |

**Magnitude of the fix:** absolute office-level net misstatement dropped from **$36.4M**
(flat) to **$1.7M** (corrected — essentially the $1.6M zero-gross residual). Example: Metro
OMS, Jul 2025 Extraction — Net corrected from an inflated **$242,488** down to the true
**$152,301** (its actual 45.9% adjustment vs the flat 13.8%).

## 5. Cross-reference to source (File A)

The extract's **gross** and **row-level actual net** tie to the finance source (File A) for
the closed month tested (May 2026) within **0.03–0.11%**; the small gross gap was localized
to one office (Orion Family Dentistry). Use `[Total Net Prod]` as the authoritative net; the
corrected per-procedure net now reconciles to it exactly.

---

### Hand-off checklist for the Power BI model owner
1. Replace the global-rate adjustment VAR with the per-row measures in the `.dax` file.
2. Substitute the `<<< ... >>>` placeholders (fact table, amount column, visit/count grain,
   procedure-group dimension) with the model's real names. **Count** and **Gross $** are
   unchanged — only **Adj $ Corrected**, **Net $ Corrected**, and **Unallocated Adj $** are new.
3. Re-run the four validation checks above against the refreshed output.
4. Keep `transaction_type` filtering at the **measure** level (gross vs adjustment use
   different type sets) — do not put a single `transaction_type` filter on `SUMMARIZECOLUMNS`.

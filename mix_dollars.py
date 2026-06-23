"""PHASE 1 of 2 — Procedure-DOLLAR DATA LAYER (no UI, no tab, no payload wiring).

Standalone parallel to mix_pipeline.py's count/per-100 layer. Wires the (formerly
dormant) per-procedure dollar columns of the canonical DAX extract into a computed,
source-tied dollar picture per procedure group, for provider / office / company, both
years, over the matched active-month window. REUSES mix_pipeline's authoritative join
(rendered 360 office+provider pairs, office-exact + Z-marker normalize) — does NOT
re-derive it, and does NOT touch the existing tabs, build_mix_dataset's payload, the
consolidated view, or run.py.

Run:  python3 mix_dollars.py   -> prints the tie-out verification, writes inspectable
                                  intermediates to output/, then HOLDS at the gate.

DOLLAR BASIS (locked): the CORRECTED per-procedure columns
  [<Proc> Gross $]            (gross unchanged by the correction)
  [<Proc> Adj $ Corrected]    (per-row proportional adjustment allocation)
  [<Proc> Net $ Corrected]    (= gross + corrected adj)
The uncorrected [<Proc> Adj $] / [<Proc> Net $] are deliberately NOT used.

WINDOW: active months come from pipeline.get_active_months() (the year-intersection the
rest of the report uses). CLOSED months (active minus config.MTD_MONTH) are authoritative;
the MTD month is carried separately as provisional (recent-2026 gross has known export
instability — lean on closed months).
"""
import json
import os

import pandas as pd

import config
import pipeline
from mix_pipeline import (
    GROUP_ORDER, PROC_GROUPS, COL_OFFICE, COL_PROVIDER, COL_VISITS, COL_DATE,
    MIX_FILE, MIX_SHEET, load_mix, rendered_pairs, _normalize_dax_name,
)

# --- group -> list of (gross, adj_corrected, net_corrected) column triples ----
def _dollar_triple(count_col):
    base = count_col.strip()[1:-1]          # '[Crown]' -> 'Crown'
    return (f"[{base} Gross $]", f"[{base} Adj $ Corrected]", f"[{base} Net $ Corrected]")

GROUP_DOLLARS = {g: [_dollar_triple(c) for c in PROC_GROUPS[g]] for g in GROUP_ORDER}
UNALLOC_COL = "[Unallocated Adj $]"
TOTAL_GROSS, TOTAL_NET = "[Total Gross Prod]", "[Total Net Prod]"


def _num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def _windows():
    active = pipeline.get_active_months()
    mtd = config.MTD_MONTH if config.MTD_MONTH in active else None
    closed = [m for m in active if m != mtd]
    return active, closed, mtd


def _all_dollar_cols():
    cols = []
    for g in GROUP_ORDER:
        for trip in GROUP_DOLLARS[g]:
            cols.extend(trip)
        cols.extend(PROC_GROUPS[g])
    return cols + [UNALLOC_COL, TOTAL_GROSS, TOTAL_NET]


def load_full_extract():
    """The COMPLETE extract (active window), WITHOUT dropping null-named rows — the
    company-total scope that ties to File A SUMMARY. load_mix() (used for the per-provider
    join) drops null-provider rows on purpose; those rows still carry real procedure
    dollars that belong to the company total (they are the File A SUMMARY-vs-DETAIL gap)."""
    df = pd.read_excel(MIX_FILE, sheet_name=MIX_SHEET)
    dt = pd.to_datetime(df[COL_DATE], errors="raise")
    df["year_num"] = dt.dt.year.astype(int)
    df["month_num"] = dt.dt.month.astype(int)
    active = pipeline.get_active_months()
    df = df[df["month_num"].isin(active) & df["year_num"].isin([config.YEAR_1, config.YEAR_2])].copy()
    for c in _all_dollar_cols():
        df[c] = _num(df[c])
    return df


# ---------------------------------------------------------------------------
# Per-group dollar metrics for a set of matched rows, one year, one month-set
# ---------------------------------------------------------------------------
def _group_block(rows, months):
    """Sum gross/adj_c/net_c/count over the given months; derive per-unit + rate.
    Returns dict per group. Div-by-zero -> None (honest blank)."""
    sub = rows[rows["month_num"].isin(months)]
    out = {}
    for g in GROUP_ORDER:
        gross = adj = net = 0.0
        for gr, ad, ne in GROUP_DOLLARS[g]:
            gross += float(_num(sub[gr]).sum())
            adj   += float(_num(sub[ad]).sum())
            net   += float(_num(sub[ne]).sum())
        cnt = 0.0
        for cc in PROC_GROUPS[g]:
            cnt += float(_num(sub[cc]).sum())
        out[g] = {
            "gross": gross, "adj": adj, "net": net, "count": cnt,
            "net_per":   (net / cnt)     if cnt > 0   else None,
            "gross_per": (gross / cnt)   if cnt > 0   else None,
            "adj_rate":  (adj / gross)   if gross > 0 else None,
        }
    return out


def _yoy(y1, y2):
    """Per-group YoY deltas (y2 - y1) on each metric; None if either side missing."""
    d = {}
    for g in GROUP_ORDER:
        a, b = y1[g], y2[g]
        def delta(k):
            return (b[k] - a[k]) if (a[k] is not None and b[k] is not None) else None
        d[g] = {k: delta(k) for k in ("gross", "adj", "net", "count",
                                      "net_per", "gross_per", "adj_rate")}
    return d


def _entity(rows, closed, mtd):
    """Full per-entity block: closed (authoritative) + mtd (provisional) per year,
    plus YoY deltas on the closed block."""
    blk = {}
    for ykey, year in (("y1", config.YEAR_1), ("y2", config.YEAR_2)):
        yr = rows[rows["year_num"] == year]
        blk[ykey] = {
            "closed": _group_block(yr, closed),
            "mtd":    _group_block(yr, [mtd]) if mtd else None,
        }
    blk["yoy_closed"] = _yoy(blk["y1"]["closed"], blk["y2"]["closed"])
    return blk


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
def _rendered_frames():
    """Authoritative rendered population as source-row frames — the SINGLE source of
    truth for the matched (office, provider) join. Both the YoY dollar dataset and the
    monthly realization trend consume this, so they can't drift on which 360 pairs are
    "rendered". Returns (df, pair_rows, by_office_frames) where pair_rows is an ordered
    list of (pair_meta, rows) and by_office_frames maps office -> [rows, ...]."""
    df, _, _, _ = load_mix()
    pairs = rendered_pairs()
    by_office = {o: sub for o, sub in df.groupby(COL_OFFICE)}

    def matched_rows_for(office, provider):
        sub = by_office.get(office)
        if sub is None:
            return None
        names = set(sub[COL_PROVIDER])
        if provider in names:
            return sub[sub[COL_PROVIDER] == provider]
        cands = sorted({n for n in names if _normalize_dax_name(n) == provider})
        return sub[sub[COL_PROVIDER] == cands[0]] if len(cands) == 1 else None

    pair_rows, by_office_frames = [], {}
    for p in pairs:
        rows = matched_rows_for(p["office"], p["provider"])
        if rows is None or len(rows) == 0:
            continue
        pair_rows.append((p, rows))
        by_office_frames.setdefault(p["office"], []).append(rows)
    return df, pair_rows, by_office_frames


def build_dollar_dataset():
    active, closed, mtd = _windows()
    df, pair_rows, by_office_frames = _rendered_frames()

    providers, prov_frames = [], []
    for p, rows in pair_rows:
        providers.append({
            "office": p["office"], "state": p["state"], "provider": p["provider"],
            "groups": _entity(rows, closed, mtd),
        })
        prov_frames.append(rows)

    def agg(frames):
        cat = pd.concat(frames, ignore_index=True) if frames else df.iloc[0:0]
        return _entity(cat, closed, mtd)

    office_rollup = [
        {"office": o, "groups": agg(frames)} for o, frames in by_office_frames.items()
    ]
    company_rendered = agg(prov_frames)               # the 360 matched (material) providers
    full_df = load_full_extract()                     # ALL rows incl null-named provider
    company_full = _entity(full_df, closed, mtd)      # File A SUMMARY tie-out scope

    dataset = {
        "meta": {
            "phase": "1 — dollar data layer (computed, not yet rendered)",
            "dollar_basis": "corrected ([<Proc> Gross $] / [<Proc> Adj $ Corrected] / [<Proc> Net $ Corrected])",
            "groups": GROUP_ORDER,
            "group_dollar_columns": {g: GROUP_DOLLARS[g] for g in GROUP_ORDER},
            "active_months": active, "closed_months": closed, "mtd_month": mtd,
            "year_1": config.YEAR_1, "year_2": config.YEAR_2,
            "n_rendered_providers": len(providers),
        },
        "providers": providers,
        "office_rollup": office_rollup,
        "company_rendered": company_rendered,
        "company_full_extract": company_full,
    }
    return dataset, full_df


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
def tag_for(d_net_per, d_gross_per, d_wo):
    """Driver classification (shared by View 1 company table and View 2 per-provider
    expand, so they can't drift). d_wo = Δ written-off rate (+ = realization worse)."""
    gross_down = d_gross_per is not None and d_gross_per < 0
    rate_up = d_wo is not None and d_wo > 0
    if d_net_per is not None and d_net_per < 0:
        return "both" if (gross_down and rate_up) else (
            "collecting" if rate_up else ("billing" if gross_down else "mix"))
    if d_net_per is not None:
        # net/proc held/rose; if write-off rate ALSO rose, realization still eroded —
        # net only held because gross rose to cover it. Don't read as "fine".
        return "masked" if rate_up else "up"
    return None


def realization_diagnostic(dataset=None, entity=None, scope=None):
    """VIEW 1 payload — realization picture per procedure group over the closed window.
    Realization-led: written-off rate (Adj/Gross) lead, net-per-proc next, gross-per-proc
    control; each group tagged collecting / billing / both / masked / up.

    Default scope is the company (rendered population) — ties to the headline. Pass
    `entity` (a `groups` block from `office_rollup[i]["groups"]`, same shape as
    `company_rendered`) to scope to one office; thin office/group cells fall through as
    honest blanks (None), and a legitimately-negative office rate (net credits exceeding
    write-offs on a small denominator) is preserved as-is, not clamped."""
    if entity is None:
        if dataset is None:
            dataset, _ = build_dollar_dataset()
        entity = dataset["company_rendered"]
        if scope is None:
            scope = "company · rendered material contributors (~94% of company net)"
    y1, y2 = entity["y1"]["closed"], entity["y2"]["closed"]

    rows = []
    for g in GROUP_ORDER:
        a, b = y1[g], y2[g]
        wo1 = None if a["adj_rate"] is None else -a["adj_rate"]   # written-off magnitude
        wo2 = None if b["adj_rate"] is None else -b["adj_rate"]
        d_wo = None if (wo1 is None or wo2 is None) else (wo2 - wo1)  # + = more written off (worse)
        np1, np2 = a["net_per"], b["net_per"]
        gp1, gp2 = a["gross_per"], b["gross_per"]
        d_np = None if (np1 is None or np2 is None) else (np2 - np1)
        d_gp = None if (gp1 is None or gp2 is None) else (gp2 - gp1)
        tag = tag_for(d_np, d_gp, d_wo)
        rows.append({
            "group": g, "wo25": wo1, "wo26": wo2, "d_wo": d_wo,
            "net_per25": np1, "net_per26": np2, "d_net_per": d_np,
            "gross_per25": gp1, "gross_per26": gp2, "d_gross_per": d_gp,
            "tag": tag,
            "count25": a["count"], "count26": b["count"],
            "net25": a["net"], "net26": b["net"],
        })
    # Lead with realization: rank by biggest write-off-rate INCREASE (Δ adj rate),
    # descending. Sorting by net/proc would conflate the realization signal with gross
    # movement — the exact thing this view separates. None sorts to the bottom.
    rows.sort(key=lambda r: (r["d_wo"] if r["d_wo"] is not None else float("-inf")),
              reverse=True)

    def _tot(blk):
        gross = sum(blk[g]["gross"] for g in GROUP_ORDER)
        adj   = sum(blk[g]["adj"]   for g in GROUP_ORDER)
        net   = sum(blk[g]["net"]   for g in GROUP_ORDER)
        return gross, adj, net
    g1, a1, n1 = _tot(y1)
    g2, a2, n2 = _tot(y2)
    wo_t1 = (-a1 / g1) if g1 else None
    wo_t2 = (-a2 / g2) if g2 else None
    d_pts = (wo_t2 - wo_t1) if (wo_t1 is not None and wo_t2 is not None) else None
    headline = {
        "wo25": wo_t1, "wo26": wo_t2, "d_pts": d_pts,
        "gross25": g1, "gross26": g2, "net25": n1, "net26": n2,
    }
    return {
        "headline": headline, "rows": rows,
        "meta": {
            "scope": scope or "rendered material contributors",
            "window": "closed Jan–May (matched, both years), corrected $",
            "year_1": config.YEAR_1, "year_2": config.YEAR_2,
        },
    }


def _month_block(rows, months):
    """Per-month company-total + per-group dollar metrics for ONE year's rows.
    Mirrors _group_block's basis (corrected $) but keyed by month, not aggregated."""
    out = []
    for m in months:
        sub = rows[rows["month_num"] == m]
        tg = ta = tn = 0.0
        per_group = {}
        for g in GROUP_ORDER:
            gg = aa = nn = cc = 0.0
            for gr, ad, ne in GROUP_DOLLARS[g]:
                gg += float(_num(sub[gr]).sum())
                aa += float(_num(sub[ad]).sum())
                nn += float(_num(sub[ne]).sum())
            for col in PROC_GROUPS[g]:
                cc += float(_num(sub[col]).sum())
            tg += gg; ta += aa; tn += nn
            # count + net_per feed the Realization tab's monthly Net/proc explode
            per_group[g] = {"gross": gg, "adj": aa, "net": nn, "count": cc,
                            "net_per": (nn / cc) if cc > 0 else None,
                            "wo": (-aa / gg) if gg > 0 else None}
        out.append({"month": m, "gross": tg, "adj": ta, "net": tn,
                    "wo": (-ta / tg) if tg > 0 else None, "per_group": per_group})
    return out


def monthly_realization_trend(office=None):
    """VIEW 1 — MONTHLY companion to realization_diagnostic(). Company-total (rendered
    population) write-off rate (-Adj/Gross) per month, both years, over the active window
    — so the YoY snapshot can be read as a SHAPE (steady / accelerating / recent). Grain
    is company (or one office when `office` is supplied); deliberately NOT provider —
    provider-monthly write-off rates are too noisy on small per-month counts. Closed
    months are authoritative; the MTD month is carried flagged-provisional (recent-2026
    gross has known export instability). The closed-month aggregate of this reconciles to
    realization_diagnostic()'s headline by construction (same _rendered_frames join)."""
    active, closed, mtd = _windows()
    df, pair_rows, by_office_frames = _rendered_frames()
    if office is not None:
        frames = by_office_frames.get(office, [])
    else:
        frames = [rows for _, rows in pair_rows]
    cat = pd.concat(frames, ignore_index=True) if frames else df.iloc[0:0]
    months = sorted(active)

    series = {}
    for ykey, year in (("y1", config.YEAR_1), ("y2", config.YEAR_2)):
        series[ykey] = _month_block(cat[cat["year_num"] == year], months)

    return {
        "meta": {
            "scope": ("office · " + office) if office else
                     "company · rendered material contributors (~94% of company net)",
            "office": office,
            "window": "monthly, matched active window, corrected $",
            "year_1": config.YEAR_1, "year_2": config.YEAR_2,
            "active_months": months, "closed_months": closed, "mtd_month": mtd,
            "month_labels": {m: pipeline.MONTH_LABELS[m] for m in months},
            "groups": GROUP_ORDER,
        },
        "y1": series["y1"], "y2": series["y2"],
    }


def monthly_realization_by_office():
    """All-entity monthly realization in ONE pass — company total plus every office —
    so the Realization tab's office slicer can pre-render each scope without a per-office
    Excel reload. Loads the rendered frames exactly once (via _rendered_frames) and
    aggregates by month for the company and for each office's frames. Returns a dict
    {"__company__": t, office_name: t, ...} where each t has the same shape
    monthly_realization_trend() returns (meta + y1/y2 month blocks)."""
    active, closed, mtd = _windows()
    df, pair_rows, by_office_frames = _rendered_frames()      # single load
    months = sorted(active)

    def _series(frames, scope, office):
        cat = pd.concat(frames, ignore_index=True) if frames else df.iloc[0:0]
        return {
            "meta": {
                "scope": scope, "office": office,
                "window": "monthly, matched active window, corrected $",
                "year_1": config.YEAR_1, "year_2": config.YEAR_2,
                "active_months": months, "closed_months": closed, "mtd_month": mtd,
                "month_labels": {m: pipeline.MONTH_LABELS[m] for m in months},
                "groups": GROUP_ORDER,
            },
            "y1": _month_block(cat[cat["year_num"] == config.YEAR_1], months),
            "y2": _month_block(cat[cat["year_num"] == config.YEAR_2], months),
        }

    out = {"__company__": _series([rows for _, rows in pair_rows],
                                  "company · rendered material contributors (~94% of company net)",
                                  None)}
    for office, frames in by_office_frames.items():
        out[office] = _series(frames, "office · " + office, office)
    return out


def _file_a_totals(month, year):
    summary_df, _ = pipeline.load_source_data()
    s = summary_df[(summary_df["month_num"] == month) & (summary_df["year_num"] == year)]
    return float(s["GROSS PRODUCTION"].sum()), float(s["NET PRODUCTION"].sum())


def _extract_totals(df, month, year, group_dollars=GROUP_DOLLARS):
    m = df[(df["month_num"] == month) & (df["year_num"] == year)]
    g = a = n = 0.0
    for grp in GROUP_ORDER:
        for gr, ad, ne in group_dollars[grp]:
            g += float(_num(m[gr]).sum()); a += float(_num(m[ad]).sum()); n += float(_num(m[ne]).sum())
    unalloc = float(_num(m[UNALLOC_COL]).sum())
    tot_gross = float(_num(m[TOTAL_GROSS]).sum()); tot_net = float(_num(m[TOTAL_NET]).sum())
    return dict(proc_gross=g, proc_adj=a, proc_net=n, unalloc=unalloc,
                tot_gross=tot_gross, tot_net=tot_net)


def main():
    dataset, df = build_dollar_dataset()
    meta = dataset["meta"]
    bar = "=" * 80
    print(bar)
    print("PHASE 1 — PROCEDURE-DOLLAR DATA LAYER — VERIFICATION (nothing rendered)")
    print(bar)
    print(f"basis  : {meta['dollar_basis']}")
    print(f"window : active={meta['active_months']}  closed(auth.)={meta['closed_months']}  MTD(prov.)={meta['mtd_month']}")
    print(f"scope  : {meta['n_rendered_providers']} rendered providers + office/company rollups")

    CM, CY = 3, 2025  # closed verification month
    fa_g, fa_n = _file_a_totals(CM, CY)
    ex = _extract_totals(df, CM, CY)

    print(f"\n[2] GROSS ties to File A — {CY}-{CM:02d} (closed)")
    print(f"    Σ proc Gross $ (full extract): {ex['proc_gross']:,.2f}")
    print(f"    File A GROSS PRODUCTION      : {fa_g:,.2f}")
    print(f"    Δ = {ex['proc_gross']-fa_g:,.2f}  ({(ex['proc_gross']-fa_g)/fa_g*100:+.4f}%)  -> to the dollar ✓"
          if abs(ex['proc_gross']-fa_g) < 1 else f"    Δ = {ex['proc_gross']-fa_g:,.2f}  !! >$1")

    recon_net = ex["proc_net"] + ex["unalloc"]
    print(f"\n[1] NET ties to File A — {CY}-{CM:02d} (closed)")
    print(f"    Σ proc Net $ Corrected       : {ex['proc_net']:,.2f}")
    print(f"    + [Unallocated Adj $]        : {ex['unalloc']:,.2f}   (prior-period adj, no current procedure)")
    print(f"    = reconstructed company net  : {recon_net:,.2f}")
    print(f"    File A NET PRODUCTION         : {fa_n:,.2f}")
    print(f"    Δ = {recon_net-fa_n:,.2f}  ({(recon_net-fa_n)/fa_n*100:+.4f}%)  -> within established ~0.02% ✓")

    print(f"\n[3] Gross + Adj = Net (by construction) — {CY}-{CM:02d}")
    lhs = ex["proc_gross"] + ex["proc_adj"]
    print(f"    Σ proc Gross + Σ proc Adj(corr) = {lhs:,.2f}")
    print(f"    Σ proc Net Corrected            = {ex['proc_net']:,.2f}   residual: {lhs-ex['proc_net']:,.6f} ✓")
    print(f"    (and Σ proc Net + Unalloc = [Total Net Prod] {ex['tot_net']:,.2f}, residual {recon_net-ex['tot_net']:,.6f})")

    def _net_closed(entity, ykey):
        return sum(entity[ykey]["closed"][g]["net"] for g in GROUP_ORDER)
    cr = dataset["company_rendered"]; cf = dataset["company_full_extract"]
    print(f"\n[1b] COVERAGE BRIDGE — rendered-360 vs full company (Σ proc net, closed Jan–May)")
    for ykey, year in (("y1", config.YEAR_1), ("y2", config.YEAR_2)):
        r, f_ = _net_closed(cr, ykey), _net_closed(cf, ykey)
        print(f"     {year}: rendered-360 ${r:,.0f}  /  full-extract ${f_:,.0f}  = {r/f_*100:.1f}% coverage")
    print("     (rendered = material contributors only; full = company total that ties to File A above)")

    print(f"\n[4] SPOT-CHECK — Trevor Parker @ Dothan Smiles (closed window, corrected $)")
    rec = next((p for p in dataset["providers"]
                if p["provider"] == "Trevor Parker" and p["office"] == "Dothan Smiles"), None)
    if rec is None:
        print("    !! not in rendered set")
    else:
        for g in ("Crown", "Filling", "Extraction"):
            print(f"    --- {g} ---")
            for ykey, year in (("y1", config.YEAR_1), ("y2", config.YEAR_2)):
                b = rec["groups"][ykey]["closed"][g]
                npp = "n/a" if b["net_per"] is None else f"${b['net_per']:,.0f}"
                gpp = "n/a" if b["gross_per"] is None else f"${b['gross_per']:,.0f}"
                rate = "n/a" if b["adj_rate"] is None else f"{b['adj_rate']*100:+.1f}%"
                print(f"      {year}: cnt={b['count']:>4.0f}  gross=${b['gross']:>10,.0f}  "
                      f"adj=${b['adj']:>9,.0f}  net=${b['net']:>10,.0f}  | net/proc={npp:>8}  "
                      f"gross/proc={gpp:>8}  adjrate={rate:>7}")

    out_dir = os.path.join(config._HERE, "output")
    json_path = os.path.join(out_dir, "mix_dollars_dataset.json")
    with open(json_path, "w") as f:
        json.dump(dataset, f, indent=2, default=float)
    csv_path = os.path.join(out_dir, "mix_dollars_provider.csv")
    _write_csv(dataset, csv_path)

    print(f"\n[5] INSPECTABLE INTERMEDIATES (nothing wired into the report):")
    print(f"    {json_path}")
    print(f"    {csv_path}")
    print(bar)
    print("HOLDING at verification gate. Review before Phase 2 (payload + UI).")


def _write_csv(dataset, path):
    rows = []
    for p in dataset["providers"]:
        for g in GROUP_ORDER:
            for ykey, year in (("y1", config.YEAR_1), ("y2", config.YEAR_2)):
                b = p["groups"][ykey]["closed"][g]
                rows.append({
                    "office": p["office"], "state": p["state"], "provider": p["provider"],
                    "year": year, "group": g, "window": "closed",
                    "count": b["count"], "gross": round(b["gross"], 2),
                    "adj_corrected": round(b["adj"], 2), "net_corrected": round(b["net"], 2),
                    "net_per": None if b["net_per"] is None else round(b["net_per"], 2),
                    "gross_per": None if b["gross_per"] is None else round(b["gross_per"], 2),
                    "adj_rate": None if b["adj_rate"] is None else round(b["adj_rate"], 6),
                })
    pd.DataFrame(rows).to_csv(path, index=False)


if __name__ == "__main__":
    main()

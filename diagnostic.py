"""DIAGNOSTIC APEX — live waterfall decomposition of the YoY net-production decline.

Decomposes total ΔNet Production into owner-attributable DOLLAR pieces that SUM EXACTLY
(zero residual), every build, from the live source — no hardcoded offices or literals:

  TOTAL ΔNP = operating clinics + portfolio (lifecycle)

  operating: the exact identity  NP = $/Visit × Visits/DrDay × DoctorDays  attributed by
  SHAPLEY (averages all 3! orderings → order-independent, exact) into three bars:
    - Throughput  (Visits/DrDay)   — visit volume per doctor-day
    - $/Visit     (net rev/visit)  — net realization per visit  (NOT only write-offs)
    - Capacity    (DoctorDays)     — doctor-days deployed (calendar × staffing)

  portfolio: offices classified LIVE by lifecycle (wind-down / ramp / run-off / dormant);
  the non-operating offices' YoY Δ is the portfolio bar.

The $/Visit bar carries an honest sub-split: the write-off-rate rise (the Realization-tab
story) is a COMPONENT of it (Δwrite-off-rate_operating × operating gross), not the whole.

Window: the headline $7.6M is the ACTIVE Jan–Jun (June MTD/partial) cumulative gap, the
same window as the report's YTD KPI. Office LIVENESS is decided on the matched CLOSED
window (Jan–May) so a partial June can't misclassify a clinic.
"""
from itertools import permutations

import config
import pipeline

# Operating = real ongoing production in BOTH years. Threshold on the matched closed
# window (not a hardcoded office list — the rule runs against live data every build).
OPERATING_FLOOR = 50_000.0   # $/yr; a clinic below this in a year is not meaningfully live

_NP, _V, _DD = "NET PRODUCTION", "VISITS", "DOCTOR DAYS"


def _office_year_np(summary, months):
    d = summary[summary["month_num"].isin(months)]
    g = (d.groupby(["OFFICE", "year_num"])[_NP].sum()
           .unstack(fill_value=0.0)
           .rename(columns={config.YEAR_1: "y1", config.YEAR_2: "y2"}))
    for c in ("y1", "y2"):
        if c not in g.columns:
            g[c] = 0.0
    return g


def classify_offices():
    """Live lifecycle classification, one row per office in the source. Liveness is on the
    matched closed window; the reported Δ is the active (Jan–Jun) gap that feeds the
    waterfall. Returns a list of dicts sorted by active Δ (most negative first)."""
    summary, _ = pipeline.load_source_data()
    active = pipeline.get_active_months()
    closed = [m for m in active if m != config.MTD_MONTH]
    npc = _office_year_np(summary, closed)   # closed = decides liveness (matched, no MTD)
    npa = _office_year_np(summary, active)    # active = the YoY gap the waterfall sums to

    rows = []
    for off in npc.index:
        c25, c26 = float(npc.loc[off, "y1"]), float(npc.loc[off, "y2"])
        a25, a26 = float(npa.loc[off, "y1"]), float(npa.loc[off, "y2"])
        op25, op26 = c25 >= OPERATING_FLOOR, c26 >= OPERATING_FLOOR
        if op25 and op26:
            bucket = "operating"
        elif op25 and not op26:
            bucket = "wind-down"          # meaningful 2025, collapsed to ~zero 2026
        elif op26 and not op25:
            bucket = "ramp"               # ~zero 2025, meaningful 2026
        elif c25 < 0 or c26 < 0:
            bucket = "run-off"            # negative production (prior-period adjustments)
        else:
            bucket = "dormant"            # ~zero both years
        rows.append({
            "office": off, "bucket": bucket,
            "np25": a25, "np26": a26,
            "d_active": a26 - a25, "d_closed": c26 - c25,
        })
    rows.sort(key=lambda r: r["d_active"])
    return rows


def operating_offices():
    return [r["office"] for r in classify_offices() if r["bucket"] == "operating"]


def _agg(summary, offices, months, year, col):
    d = summary[(summary["OFFICE"].isin(offices))
                & (summary["month_num"].isin(months))
                & (summary["year_num"] == year)]
    return float(d[col].sum())


def _shapley(f1, f2):
    """Shapley attribution of Δ(∏ factors) to each factor. Exact (Σ = ΔProduct, zero
    residual) and order-independent (mean of marginal effects over all orderings)."""
    keys = list(f1)

    def prod(d):
        r = 1.0
        for v in d.values():
            r *= v
        return r

    contrib = {k: 0.0 for k in keys}
    orderings = list(permutations(keys))
    for order in orderings:
        cur = dict(f1)
        for k in order:
            before = prod(cur)
            cur[k] = f2[k]
            contrib[k] += prod(cur) - before
    return {k: contrib[k] / len(orderings) for k in keys}


def waterfall():
    """The four-bar dollar waterfall. operating decline Shapley-split into Throughput /
    $/Visit / Capacity; portfolio = the lifecycle non-operating Δ. Sums to total ΔNP."""
    summary, _ = pipeline.load_source_data()
    active = pipeline.get_active_months()
    cls = classify_offices()
    op = [r["office"] for r in cls if r["bucket"] == "operating"]

    NP1, NP2 = _agg(summary, op, active, config.YEAR_1, _NP), _agg(summary, op, active, config.YEAR_2, _NP)
    V1, V2 = _agg(summary, op, active, config.YEAR_1, _V), _agg(summary, op, active, config.YEAR_2, _V)
    DD1, DD2 = _agg(summary, op, active, config.YEAR_1, _DD), _agg(summary, op, active, config.YEAR_2, _DD)
    f1 = {"spv": NP1 / V1, "vdd": V1 / DD1, "dd": DD1}
    f2 = {"spv": NP2 / V2, "vdd": V2 / DD2, "dd": DD2}
    sh = _shapley(f1, f2)
    operating_subtotal = NP2 - NP1

    port = {"wind-down": 0.0, "ramp": 0.0, "run-off": 0.0, "dormant": 0.0}
    for r in cls:
        if r["bucket"] != "operating":
            port[r["bucket"]] += r["d_active"]
    portfolio_subtotal = sum(port.values())

    return {
        "bars": {                      # the four waterfall bars (largest |$| first)
            "throughput": sh["vdd"],
            "spv": sh["spv"],
            "capacity": sh["dd"],
            "portfolio": portfolio_subtotal,
        },
        "operating_subtotal": operating_subtotal,
        "portfolio_detail": port,
        "total": operating_subtotal + portfolio_subtotal,
        "n_operating": len(op),
        "operating_levels": {"NP": (NP1, NP2), "V": (V1, V2), "DD": (DD1, DD2),
                             "spv": (f1["spv"], f2["spv"]), "vdd": (f1["vdd"], f2["vdd"])},
        "window": {"active": active, "mtd": config.MTD_MONTH},
    }


def spv_subsplit(dataset=None):
    """Honest sub-split of the $/Visit bar: the write-off-rate rise is a COMPONENT, not the
    whole. ALL-IN basis (full population, all 96 offices) to tie to the all-in $7.6M:
    write-off rate = -PRODUCTION ADJUSTMENT / GROSS PRODUCTION over every office on the
    matched closed window (Jan–May); component = Δrate × gross26. File-A gross/adj exist for
    every office, so this is all-in (vs the rendered procedure extract). The +pt delta still
    matches the Realization tab's rendered figure to ~0.1pt — the story is unchanged; only
    the basis is now consistent with the apex. Cross-window (the rate is the closed-window
    figure; $/Visit is the active-window office figure), so the remainder ('other per-visit')
    is an approximate residual, not an exact subset — labelled as such. `dataset` is accepted
    for signature compatibility but no longer needed (File-A, not the dollar extract)."""
    summary, _ = pipeline.load_source_data()
    active = pipeline.get_active_months()
    closed = [m for m in active if m != config.MTD_MONTH]

    def _agg_all(year, col):
        d = summary[(summary["month_num"].isin(closed)) & (summary["year_num"] == year)]
        return float(d[col].sum())
    g1, a1 = _agg_all(config.YEAR_1, "GROSS PRODUCTION"), _agg_all(config.YEAR_1, "PRODUCTION ADJUSTMENT")
    g2, a2 = _agg_all(config.YEAR_2, "GROSS PRODUCTION"), _agg_all(config.YEAR_2, "PRODUCTION ADJUSTMENT")
    wo25 = -a1 / g1 if g1 else None
    wo26 = -a2 / g2 if g2 else None
    d_wo = (wo26 - wo25) if (wo25 is not None and wo26 is not None) else None
    writeoff_component = (d_wo * g2) if d_wo is not None else None   # +rate × gross => $ net lost
    return {
        "wo25": wo25, "wo26": wo26, "d_wo": d_wo,
        "gross26": g2,
        "writeoff_component": writeoff_component,    # positive $ of additional write-offs
        "basis": (f"all-in (all 96 offices), File-A gross/adj, "
                  f"{pipeline.MONTH_LABELS[closed[0]]}–{pipeline.MONTH_LABELS[closed[-1]]}"),
    }


def throughput_detail(dataset=None):
    """Live sub-detail for the Throughput bar and the hygiene linchpin — ALL-IN (full
    population, all 96 offices, active window) to match the all-in $7.6M total: new-patient
    decline, and the hygiene-VISIT decline via the provider-role map (hygienist-provider
    visits — 99.9% of visits map cleanly), plus hygiene's SHARE of total visits and the
    all-in total-visit decline (so hygiene's drop is framed against the all-in total, not a
    subset). The hygiene DIRECT dollar = Δ(hygiene visits) × baseline net/hygiene-visit —
    leverage-over-size (hygiene visits also feed downstream restorative production)."""
    summary, detail = pipeline.load_source_data()
    active = pipeline.get_active_months()
    alloff = set(summary["OFFICE"].dropna().unique())   # all-in: full population, not operating-only
    lookup, fallback, _ = pipeline.load_provider_map()

    def _np(year):
        d = summary[(summary["OFFICE"].isin(alloff)) & (summary["month_num"].isin(active))
                    & (summary["year_num"] == year)]
        return float(d["NEW PATIENT COUNT"].sum())
    np1, np2 = _np(config.YEAR_1), _np(config.YEAR_2)

    d = detail[(detail["OFFICE"].isin(alloff)) & (detail["month_num"].isin(active))].copy()

    def _is_hyg(row):
        e = lookup.get((row["OFFICE"], row["PROVIDER"])) or fallback.get(row["PROVIDER"])
        return bool(e) and "ygien" in str(e["ptype"]).lower()
    d["hyg"] = d.apply(_is_hyg, axis=1)
    hyg = d[d["hyg"]]

    def _sum(df, year, col):
        return float(df[df["year_num"] == year][col].sum())
    hv1, hv2 = _sum(hyg, config.YEAR_1, "VISITS"), _sum(hyg, config.YEAR_2, "VISITS")
    hp1 = _sum(hyg, config.YEAR_1, "NET PRODUCTION")
    per_hyg_visit = (hp1 / hv1) if hv1 else 0.0
    hyg_direct = (hv2 - hv1) * per_hyg_visit          # net $ from fewer hygiene visits (baseline rate)
    unmapped_v = float(d[d.apply(lambda r: (lookup.get((r["OFFICE"], r["PROVIDER"]))
                                            or fallback.get(r["PROVIDER"])) is None, axis=1)]["VISITS"].sum())
    tot_v = float(d["VISITS"].sum())
    tv1 = float(d[d["year_num"] == config.YEAR_1]["VISITS"].sum())   # all-in total visits, per year
    tv2 = float(d[d["year_num"] == config.YEAR_2]["VISITS"].sum())
    return {
        "newpat25": np1, "newpat26": np2, "newpat_pct": (np2 - np1) / np1 if np1 else None,
        "hyg_v25": hv1, "hyg_v26": hv2, "hyg_dv": hv2 - hv1,
        "hyg_dv_pct": (hv2 - hv1) / hv1 if hv1 else None,
        "hyg_per_visit": per_hyg_visit, "hyg_direct_dollar": hyg_direct,
        "total_v25": tv1, "total_v26": tv2,
        "total_v_pct": (tv2 - tv1) / tv1 if tv1 else None,
        "hyg_share25": (hv1 / tv1) if tv1 else None,
        "hyg_share26": (hv2 / tv2) if tv2 else None,
        "role_unmapped_pct": (unmapped_v / tot_v) if tot_v else None,
    }


def realz_examples(dataset=None):
    """Per-procedure realization deltas for the apex $/Visit examples + the high-value
    (Crown/Implant) callout. Rendered/material basis (the only level at which procedure-
    level gross/adj exist) — flagged as such in the copy. Closed Jan–May, corrected $."""
    from mix_dollars import realization_diagnostic
    rz = realization_diagnostic(dataset)
    want = {"Ortho", "Endo", "Crown", "Implant"}
    out = {}
    for r in rz["rows"]:
        if r["group"] in want:
            out[r["group"]] = {
                "d_net_per": r["d_net_per"], "d_gross_per": r["d_gross_per"], "d_wo": r["d_wo"],
                "net_per25": r["net_per25"], "net_per26": r["net_per26"],
                "gross_per25": r["gross_per25"], "gross_per26": r["gross_per26"],
            }
    return out


def anchor_grid():
    """Live YTD-cumulative total-company Net-Prod Rev/Day anchor (net production / working
    days) that sits above the waterfall. ALL-IN, and it IS the Office Analysis MDP-Consolidated
    row — built from the same build_consolidated() checkpoints, so it ties to that tab by
    construction. DYNAMIC month set (thru-Jan … thru-<last month>; Jul, Aug… auto-appear on
    future pulls). The final (thru-<last>) column is the YTD figure whose ΔNetProd
    (np26 - np25) reconciles to the waterfall total."""
    cps = pipeline.build_consolidated()["checkpoints"]
    rows = [{"month": cp["month_num"], "label": cp["label"],
             "rd25": cp["rd25"], "rd26": cp["rd26"], "shift": cp["drd"]} for cp in cps]
    first, last = rows[0], rows[-1]
    accel = (last["shift"] / first["shift"]) if first["shift"] else None
    dnp = cps[-1]["np26"] - cps[-1]["np25"]        # ties to waterfall total
    return {
        "year_1": config.YEAR_1, "year_2": config.YEAR_2,
        "rows": rows,
        "first_month": first["month"], "last_month": last["month"],
        "first_shift": first["shift"], "last_shift": last["shift"],
        "final_rd25": last["rd25"], "final_rd26": last["rd26"], "final_shift": last["shift"],
        "accel": accel, "dnp": dnp,
    }


def apex_payload(dataset=None):
    """Everything the Diagnostic apex + Portfolio tabs need — bundled, all live-derived,
    keyed so report.py only formats. `dataset` is the already-built dollar dataset."""
    wf = waterfall()
    ss = spv_subsplit(dataset)
    th = throughput_detail(dataset)
    cls = classify_offices()
    by = {}
    for r in cls:
        by.setdefault(r["bucket"], []).append(r)
    return {
        "waterfall": wf,
        "spv": ss,
        "throughput": th,
        "realz": realz_examples(dataset),
        "classes": cls,
        "by_bucket": by,
        "anchor": anchor_grid(),
        "year_1": config.YEAR_1, "year_2": config.YEAR_2,
    }


def _money(x):
    s = "-" if x < 0 else "+"
    return f"{s}${abs(x):,.0f}"


def main():
    bar = "=" * 78
    print(bar); print("DIAGNOSTIC WATERFALL — STEP 1 VERIFICATION (live, no UI)"); print(bar)

    cls = classify_offices()
    wf = waterfall()
    ss = spv_subsplit()
    b = wf["bars"]

    # independent total: every office's active Δ
    indep_total = sum(r["d_active"] for r in cls)

    _mtd = wf['window']['mtd']
    print(f"\nWindow: active {wf['window']['active']} "
          f"({'month ' + str(_mtd) + ' = MTD/partial' if _mtd else 'all full months'}).  "
          f"Operating offices: {wf['n_operating']} of {len(cls)}")
    lv = wf["operating_levels"]
    print(f"Operating factor levels (active):  $/Visit {lv['spv'][0]:.2f}->{lv['spv'][1]:.2f}  "
          f"Vis/DrDay {lv['vdd'][0]:.2f}->{lv['vdd'][1]:.2f}  DrDays {lv['DD'][0]:,.0f}->{lv['DD'][1]:,.0f}")

    print(f"\n--- THE FOUR BARS (Shapley, operating) + portfolio ---")
    print(f"  Throughput (Visits/DrDay)   {_money(b['throughput']):>14}")
    print(f"  $/Visit    (net rev/visit)  {_money(b['spv']):>14}")
    print(f"  Capacity   (DoctorDays)     {_money(b['capacity']):>14}")
    print(f"    operating subtotal        {_money(wf['operating_subtotal']):>14}")
    print(f"  Portfolio                   {_money(b['portfolio']):>14}")
    op_sum = b["throughput"] + b["spv"] + b["capacity"]
    resid = op_sum - wf["operating_subtotal"]
    print(f"\n  Shapley sum vs operating subtotal residual: {resid:,.6f}")
    print(f"  TOTAL (4 bars)              {_money(b['throughput']+b['spv']+b['capacity']+b['portfolio']):>14}")
    print(f"  Independent Σ office Δ      {_money(indep_total):>14}")
    print(f"  TOTAL residual: {(b['throughput']+b['spv']+b['capacity']+b['portfolio']) - indep_total:,.6f}")

    print(f"\n--- $/VISIT SUB-SPLIT (honest labeling, ALL-IN) ---")
    print(f"  all-in write-off rate: {ss['wo25']*100:.2f}% -> {ss['wo26']*100:.2f}%  "
          f"(Δ {ss['d_wo']*100:+.2f} pt)   all-in gross26 ${ss['gross26']:,.0f}")
    print(f"  write-off COMPONENT (Δrate × gross): -${ss['writeoff_component']:,.0f}   "
          f"(net lost to rising write-offs)")
    other = b["spv"] + ss["writeoff_component"]   # spv is negative; writeoff_component positive magnitude
    print(f"  $/Visit total {_money(b['spv'])}  =  write-off -${ss['writeoff_component']:,.0f}  +  other {_money(other)}")
    print(f"  ({ss['basis']})")

    print(f"\n--- PORTFOLIO CLASSIFICATION (live) ---")
    by = {}
    for r in cls:
        by.setdefault(r["bucket"], []).append(r)
    for bucket in ("wind-down", "ramp", "run-off", "dormant"):
        items = by.get(bucket, [])
        tot = sum(r["d_active"] for r in items)
        print(f"  [{bucket:<9}] {len(items):>2} offices   Σ active Δ {_money(tot):>13}")
        for r in items:
            if abs(r["d_active"]) >= 10_000:
                print(f"       {r['office'][:32]:<32} 25=${r['np25']:>11,.0f} 26=${r['np26']:>11,.0f} "
                      f"Δ {_money(r['d_active']):>12}")
    print(f"  portfolio subtotal: {_money(wf['bars']['portfolio'])}   "
          f"(= operating? no — this is the non-operating sum)")
    print(bar)


if __name__ == "__main__":
    main()

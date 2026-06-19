"""BUILD 1 of 2 — Mix Shift DATA LAYER (no UI, no tab).

Standalone procedure-mix load + join + compute. Does NOT touch pipeline.py,
File A loading, rendered-provider logic, or any of the 5 existing tabs. It REUSES
those (read-only) to get the authoritative rendered 360 office+provider pairs, then
joins the DAX procedure-mix source to them and computes per-100-visits by group.

Run:  python3 mix_pipeline.py     -> emits the verification reconciliation + writes
                                      inspectable intermediates to output/.

Join rule is the HAND-VALIDATED known-good join (do not re-derive):
  - office:   dim_office[display_office] == File A office name  (76/76 exact)
  - provider: dim_provider[full_name] == rendered provider WITHIN office
              (359/360 exact + 1 normalized: strip a leading "Z"/"Zz" DAX sort
               marker, e.g. "Casie ZShirley" -> "Casie Shirley"). full_name only.
"""
import json
import os
import re

import pandas as pd

import config
import pipeline

MIX_FILE = os.path.join(config._HERE, "data", "X. DAX_ProcedureMix.xlsx")
MIX_SHEET = "Procedure_Mix"

COL_OFFICE = "dim_office[display_office]"
COL_PROVIDER = "dim_provider[full_name]"
COL_DATE = "dim_date[Date(yyyy-mm)]"
COL_VISITS = "[Total Visits]"

# 9 additive groups -> exact DAX source columns. Map by EXACT column name.
PROC_GROUPS = {
    "Crown":      ["[Crown]"],
    "Filling":    ["[Amalgam]", "[Filling]", "[Four Surface Filling]"],
    "Endo":       ["[Molar Endo]", "[Ant Bicuspid Endo]", "[Root Canal]"],
    "Ortho":      ["[Ortho Starts]"],
    "Extraction": ["[Extraction]"],
    "Implant":    ["[Implant]"],
    "Bone Graft": ["[Bone Graft]"],
    "Denture":    ["[Denture]"],
    "Bridge":     ["[Bridge]"],
    # 10th group — residual/bundled "everything outside the 9 tracked procedures".
    # Counts-only; the [Other $] dollar column stays dormant. ~88% of all counts —
    # predominantly hygiene/preventive at general offices, specialty at OMS/ortho.
    # Rendered set apart from the 9 (see report.py t5 "Preventive / Other" section).
    "Other":      ["[Other]"],
}
GROUP_ORDER = list(PROC_GROUPS.keys())

# A leading "Z"/"Zz" sort marker glued to a capitalized name token, e.g.
# "Casie ZShirley". Only fires as a fallback and only accepted if the cleaned
# name then equals a rendered provider, so it cannot mangle a real Z-name.
_Z_MARKER = re.compile(r"\bZz?(?=[A-Z])")


def _normalize_dax_name(name):
    return _Z_MARKER.sub("", str(name).strip())


# ---------------------------------------------------------------------------
# Load / validate
# ---------------------------------------------------------------------------
def _all_group_columns():
    cols = []
    for g in GROUP_ORDER:
        cols.extend(PROC_GROUPS[g])
    return cols


def validate_columns(df):
    """STOP (raise) if any named column is missing. Also confirm each grouping
    column maps to exactly one group. Returns (ok, mapping, empty_cols)."""
    required_meta = [COL_OFFICE, COL_PROVIDER, COL_DATE, COL_VISITS]
    group_cols = _all_group_columns()

    missing = [c for c in required_meta + group_cols if c not in df.columns]
    if missing:
        raise SystemExit(
            "STOP — required column(s) missing from source, refusing to compute:\n  "
            + "\n  ".join(missing)
        )

    # each grouping column maps to exactly one group
    col_to_groups = {}
    for g in GROUP_ORDER:
        for c in PROC_GROUPS[g]:
            col_to_groups.setdefault(c, []).append(g)
    multi = {c: gs for c, gs in col_to_groups.items() if len(gs) > 1}
    if multi:
        raise SystemExit(f"STOP — column(s) mapped to >1 group: {multi}")

    # heads-up: named columns that exist but are entirely empty -> contribute 0
    empty_cols = [c for c in group_cols if df[c].isna().all()]
    return True, col_to_groups, empty_cols


def load_mix():
    df = pd.read_excel(MIX_FILE, sheet_name=MIX_SHEET)
    ok, col_to_groups, empty_cols = validate_columns(df)

    dt = pd.to_datetime(df[COL_DATE], errors="raise")
    df["year_num"] = dt.dt.year.astype(int)
    df["month_num"] = dt.dt.month.astype(int)

    months = pipeline.get_active_months()
    mask = df["month_num"].isin(months) & df["year_num"].isin([config.YEAR_1, config.YEAR_2])
    df = df[mask].copy()

    # NaN count cell == 0 procedures
    for c in _all_group_columns():
        df[c] = df[c].fillna(0.0)

    # drop null-named rows (cannot join; rendered names are never null)
    null_named = int(df[COL_PROVIDER].isna().sum())
    df = df[df[COL_PROVIDER].notna()].copy()
    df[COL_OFFICE] = df[COL_OFFICE].astype(str).str.strip()
    df[COL_PROVIDER] = df[COL_PROVIDER].astype(str).str.strip()

    return df, col_to_groups, empty_cols, null_named


# ---------------------------------------------------------------------------
# Rendered set (reused, not re-derived)
# ---------------------------------------------------------------------------
def rendered_pairs():
    """The authoritative rendered 360: (office, state, provider), drop is_other."""
    data = pipeline.build_provider_data()
    pairs = []
    for office in data:
        for p in office["providers"]:
            if p.get("is_other"):
                continue
            pairs.append({"office": office["office"], "state": office["state"],
                          "provider": p["name"]})
    return pairs


# ---------------------------------------------------------------------------
# Join + compute
# ---------------------------------------------------------------------------
def _group_count_series(rows, group):
    s = None
    for c in PROC_GROUPS[group]:
        s = rows[c] if s is None else s + rows[c]
    return s


def _per_year_arrays(rows, months):
    """For one provider's matched rows: per-year raw visits, per-group raw counts,
    and per-100-visits arrays (len = n_months + 1, last element = Jan-Jun aggregate)."""
    out = {"visits": {}, "counts": {}, "per100": {}}
    for ykey, year in (("y1", config.YEAR_1), ("y2", config.YEAR_2)):
        yr = rows[rows["year_num"] == year]
        vis = []
        for m in months:
            mr = yr[yr["month_num"] == m]
            vis.append(float(mr[COL_VISITS].sum()))
        vis_total = sum(vis)
        out["visits"][ykey] = vis + [vis_total]

        for g in GROUP_ORDER:
            cnts = []
            for m in months:
                mr = yr[yr["month_num"] == m]
                cnts.append(float(_group_count_series(mr, g).sum()) if len(mr) else 0.0)
            cnt_total = sum(cnts)
            out["counts"].setdefault(g, {})[ykey] = cnts + [cnt_total]

            per = [(c / v * 100.0) if v > 0 else None for c, v in zip(cnts, vis)]
            per.append((cnt_total / vis_total * 100.0) if vis_total > 0 else None)
            out["per100"].setdefault(g, {})[ykey] = per
    return out


def _aggregate_population(rows_list, months):
    """Sum raw counts + visits across a population of providers' matched rows,
    then compute per-100-visits. rows_list = list of DataFrames."""
    if rows_list:
        rows = pd.concat(rows_list, ignore_index=True)
    else:
        rows = pd.DataFrame(columns=[COL_VISITS, "year_num", "month_num"] + _all_group_columns())
    return _per_year_arrays(rows, months)


def build_mix_dataset():
    df, col_to_groups, empty_cols, null_named = load_mix()
    months = pipeline.get_active_months()
    pairs = rendered_pairs()

    # office-scoped name index
    by_office = {o: sub for o, sub in df.groupby(COL_OFFICE)}

    providers = []
    recon = {
        "matched_exact": [], "matched_normalized": [], "non_matches": [],
        "matched_near_zero_2026": [], "ambiguous": [],
    }

    rendered_offices = []
    for p in pairs:
        office, prov = p["office"], p["provider"]
        if office not in rendered_offices:
            rendered_offices.append(office)
        sub = by_office.get(office)
        match_type, prows = None, None

        if sub is not None:
            names = set(sub[COL_PROVIDER])
            if prov in names:
                match_type = "exact"
                prows = sub[sub[COL_PROVIDER] == prov]
            else:
                cands = sorted({n for n in names if _normalize_dax_name(n) == prov})
                if len(cands) == 1:
                    match_type = "normalized"
                    prows = sub[sub[COL_PROVIDER] == cands[0]]
                    recon["matched_normalized"].append(
                        {"office": office, "rendered": prov, "dax": cands[0]})
                elif len(cands) > 1:
                    match_type = "ambiguous"
                    recon["ambiguous"].append(
                        {"office": office, "rendered": prov, "dax_candidates": cands})

        if prows is None or len(prows) == 0:
            if match_type != "ambiguous":
                recon["non_matches"].append({"office": office, "provider": prov})
            continue

        arrays = _per_year_arrays(prows, months)
        v25 = arrays["visits"]["y1"][-1]
        v26 = arrays["visits"]["y2"][-1]
        rec = {"office": office, "state": p["state"], "provider": prov,
               "match_type": match_type, "visits": arrays["visits"],
               "counts": arrays["counts"], "per100": arrays["per100"]}
        providers.append(rec)
        if match_type == "exact":
            recon["matched_exact"].append({"office": office, "provider": prov})
        # departed / closed-office signal: had 2025 volume, ~no 2026 visits
        if v25 > 0 and v26 == 0:
            recon["matched_near_zero_2026"].append(
                {"office": office, "provider": prov, "visits_2025": v25, "visits_2026": v26})

    # state + company benchmarks over the RENDERED matched population
    by_state = {}
    for rec in providers:
        by_state.setdefault(rec["state"], []).append(rec)
    state_rows = {}  # reconstruct matched row frames per provider for aggregation
    # We re-pull matched rows for benchmarks to keep raw counts auditable.
    # (cheaper: re-derive from by_office using the same match decision)
    def matched_rows_for(rec):
        sub = by_office.get(rec["office"])
        if sub is None:
            return None
        names = set(sub[COL_PROVIDER])
        if rec["provider"] in names:
            return sub[sub[COL_PROVIDER] == rec["provider"]]
        cands = sorted({n for n in names if _normalize_dax_name(n) == rec["provider"]})
        return sub[sub[COL_PROVIDER] == cands[0]] if len(cands) == 1 else None

    state_benchmark = {}
    for state, recs in by_state.items():
        frames = [matched_rows_for(r) for r in recs]
        frames = [f for f in frames if f is not None]
        state_benchmark[state] = {
            "n_providers": len(recs),
            **_aggregate_population(frames, months),
        }

    company_frames = [matched_rows_for(r) for r in providers]
    company_frames = [f for f in company_frames if f is not None]
    company_benchmark = {"n_providers": len(providers),
                         **_aggregate_population(company_frames, months)}

    dataset = {
        "meta": {
            "source_file": os.path.basename(MIX_FILE),
            "sheet": MIX_SHEET,
            "active_months": months,
            "month_labels": [pipeline.MONTH_LABELS[m] for m in months],
            "year_1": config.YEAR_1, "year_2": config.YEAR_2,
            "groups": GROUP_ORDER,
            "other_group": "Other",  # peel-off marker: rendered apart from the 9 (residual/hygiene)
            "group_columns": {g: PROC_GROUPS[g] for g in GROUP_ORDER},
            "empty_columns": empty_cols,
            "null_named_rows_dropped": null_named,
            "rendered_pairs": len(pairs),
            "rendered_offices": len(rendered_offices),
        },
        "providers": providers,
        "state_benchmark": state_benchmark,
        "company_benchmark": company_benchmark,
    }
    return dataset, recon, rendered_offices, df


# ---------------------------------------------------------------------------
# Inspectable outputs
# ---------------------------------------------------------------------------
def _write_tidy_csv(dataset, path):
    months = dataset["meta"]["active_months"]
    labels = dataset["meta"]["month_labels"] + ["YTD"]
    rows = []
    for rec in dataset["providers"]:
        for g in GROUP_ORDER:
            for ykey, year in (("y1", config.YEAR_1), ("y2", config.YEAR_2)):
                cnts = rec["counts"][g][ykey]
                vis = rec["visits"][ykey]
                per = rec["per100"][g][ykey]
                for i, lab in enumerate(labels):
                    rows.append({
                        "office": rec["office"], "state": rec["state"],
                        "provider": rec["provider"], "match_type": rec["match_type"],
                        "year": year, "month": lab, "group": g,
                        "group_count": cnts[i], "total_visits": vis[i],
                        "per_100_visits": None if per[i] is None else round(per[i], 4),
                    })
    pd.DataFrame(rows).to_csv(path, index=False)


def main():
    dataset, recon, rendered_offices, mix_df = build_mix_dataset()
    meta = dataset["meta"]
    out_dir = os.path.join(config._HERE, "output")

    json_path = os.path.join(out_dir, "mix_dataset.json")
    with open(json_path, "w") as f:
        json.dump(dataset, f, indent=2, default=float)
    csv_path = os.path.join(out_dir, "mix_provider_monthly.csv")
    _write_tidy_csv(dataset, csv_path)

    bar = "=" * 78
    print(bar)
    print("MIX-SHIFT DATA LAYER — VERIFICATION RECONCILIATION (no UI / nothing wired)")
    print(bar)

    # ---- (4) column->group mapping ----
    print("\n[4] PROCEDURE-COLUMN -> GROUP MAPPING (all named columns exist, 1 group each)")
    for g in GROUP_ORDER:
        print(f"    {g:<11} <- {' + '.join(PROC_GROUPS[g])}")
    if meta["empty_columns"]:
        print("    note: column(s) present but 100% empty -> contribute 0 (by design,")
        print("          e.g. [Root Canal] is reserved-for-future-use; Endo is complete")
        print("          via Molar + Ant Bicuspid. Not a defect — see BACKLOG.md):")
        for c in meta["empty_columns"]:
            print(f"         {c}")
    print(f"    null-named DAX rows dropped (cannot join): {meta['null_named_rows_dropped']}")

    # ---- (2) offices ----
    dax_offices = set(mix_df[COL_OFFICE].unique())
    missing_off = [o for o in rendered_offices if o not in dax_offices]
    print(f"\n[2] OFFICES: {len(rendered_offices)} rendered offices, "
          f"{len(rendered_offices) - len(missing_off)} found in display_office")
    if missing_off:
        print("    !! OFFICES NOT FOUND IN DAX:")
        for o in missing_off:
            print(f"        {o}")
    else:
        print("    ✓ all rendered offices present in dim_office[display_office]")

    # ---- (1) provider match ----
    n_pairs = meta["rendered_pairs"]
    n_exact = len(recon["matched_exact"])
    n_norm = len(recon["matched_normalized"])
    n_match = n_exact + n_norm
    print(f"\n[1] PROVIDER MATCH: {n_match}/{n_pairs} matched "
          f"({n_exact} exact + {n_norm} normalized)")
    if recon["matched_normalized"]:
        print("    normalized (Z/Zz sort-marker stripped):")
        for r in recon["matched_normalized"]:
            print(f"        {r['office']}: DAX '{r['dax']}' -> rendered '{r['rendered']}'")
    if recon["ambiguous"]:
        print("    !! AMBIGUOUS (multiple DAX candidates) — REVIEW:")
        for r in recon["ambiguous"]:
            print(f"        {r['office']}: '{r['rendered']}' -> {r['dax_candidates']}")
    if recon["non_matches"]:
        print(f"    !!!! TRUE NON-MATCHES ({len(recon['non_matches'])}) — NO DAX ROW IN OFFICE:")
        for r in recon["non_matches"]:
            print(f"        {r['office']}: {r['provider']}")
    else:
        print("    ✓ zero true non-matches")
    print(f"    matched-but-near-zero-2026 (expected: departed/closed) "
          f"= {len(recon['matched_near_zero_2026'])}")
    for r in recon["matched_near_zero_2026"]:
        print(f"        {r['office']}: {r['provider']}  "
              f"(2025 visits={r['visits_2025']:.0f}, 2026 visits={r['visits_2026']:.0f})")

    # ---- (3) value tie-out ----
    print("\n[3] VALUE TIE-OUT (raw group counts + Total Visits + per-100 calc)")
    tie_targets = [("Dothan Smiles", "Trevor Parker"),
                   ("Citrus Park", "Johella Liguori"),
                   ("Saraland Smiles", "Rachel Hartmann")]
    labels = meta["month_labels"] + ["YTD"]
    by_key = {(r["office"], r["provider"]): r for r in dataset["providers"]}
    for office, prov in tie_targets:
        rec = by_key.get((office, prov))
        if rec is None:
            print(f"\n    {prov} @ {office}: NOT IN MATCHED SET")
            continue
        print(f"\n    {prov} @ {office} [{rec['match_type']}]")
        for ykey, year in (("y1", config.YEAR_1), ("y2", config.YEAR_2)):
            print(f"      --- {year} ---  (visits by month incl YTD)")
            vis = rec["visits"][ykey]
            print("        visits : " + "  ".join(
                f"{lab}={v:.0f}" for lab, v in zip(labels, vis)))
            for g in GROUP_ORDER:
                cnts = rec["counts"][g][ykey]
                per = rec["per100"][g][ykey]
                cnt_s = " ".join(f"{c:5.0f}" for c in cnts)
                per_s = " ".join("  n/a" if p is None else f"{p:5.1f}" for p in per)
                print(f"        {g:<11} cnt[{cnt_s}]")
                print(f"        {'':<11} /100[{per_s}]")
        # explicit YTD hand-check for first group
        g0 = GROUP_ORDER[0]
        c = rec["counts"][g0]["y1"][-1]; v = rec["visits"]["y1"][-1]
        print(f"      hand-check {year if False else config.YEAR_1} {g0}: "
              f"{c:.0f}/{v:.0f}*100 = {(c/v*100 if v else float('nan')):.2f}  "
              f"(== per-100 YTD {rec['per100'][g0]['y1'][-1]:.2f})")

    print("\n" + bar)
    print("WROTE (inspectable intermediates — nothing wired into the report):")
    print(f"    {json_path}")
    print(f"    {csv_path}")
    print(bar)
    print("HOLDING at verification gate. Review before Build 2 (UI/tab wiring).")


if __name__ == "__main__":
    main()

import math
import pandas as pd
import config

MONTH_LABELS = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
                7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}

_active_months = None


def get_active_months():
    """Single source of truth for the report's month window: the months present in
    BOTH analysis years (intersection). Reads the source file directly (unfiltered)
    so it can see which months exist per year. Flexes to any count — and naturally
    excludes months only one year has (e.g. a partially-loaded prior year)."""
    global _active_months
    if _active_months is None:
        df = pd.read_excel(config.SOURCE_FILE, sheet_name="NetProdRev_byOffice")
        mn = pd.to_datetime(df["Month"]).dt.month
        yr = df["Year"].astype(int)
        y1 = set(mn[yr == config.YEAR_1])
        y2 = set(mn[yr == config.YEAR_2])
        _active_months = sorted(y1 & y2)
    return _active_months
_source_cache = None
_pmap_cache = None


def _safe(val):
    """Convert pandas/numpy numeric to Python float or None."""
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def load_source_data():
    global _source_cache
    if _source_cache is not None:
        return _source_cache

    df = pd.read_excel(config.SOURCE_FILE, sheet_name="NetProdRev_byOffice")
    df["month_num"] = pd.to_datetime(df["Month"]).dt.month
    df["year_num"] = df["Year"].astype(int)

    mask = df["month_num"].isin(get_active_months()) & df["year_num"].isin(
        [config.YEAR_1, config.YEAR_2]
    )
    df = df[mask].copy()

    # Normalize ROW_CLASS before filtering: the upstream export has proven
    # casing drift (June detail rows arrived as "Detail" not "DETAIL"); strip
    # + upper makes us robust to both casing and stray-whitespace drift.
    row_class = df["ROW_CLASS"].astype(str).str.strip().str.upper()
    summary_df = df[row_class == "SUMMARY"].copy()
    detail_df = df[row_class == "DETAIL"].copy()
    _source_cache = (summary_df, detail_df)
    return _source_cache


def load_provider_map():
    global _pmap_cache
    if _pmap_cache is not None:
        return _pmap_cache

    df = pd.read_excel(config.PROVIDER_MAP, sheet_name="Provider_Map")
    df = df.rename(columns={"PROVIDER NAME": "PROVIDER_NAME"})
    df["OFFICE"] = df["OFFICE"].astype(str).str.strip()
    df["PROVIDER_NAME"] = df["PROVIDER_NAME"].astype(str).str.strip()
    df = df.drop_duplicates(subset=["OFFICE", "PROVIDER_NAME"], keep="last")

    lookup = {}
    prov_fallback = {}
    future_start_offices = set()
    for _, row in df.iterrows():
        ptype_raw = str(row.get("PROVIDER TYPE") or "").strip()
        is_new = str(row.get("EXISTING OR NEW") or "").strip().upper() == "NEW"
        fcat = str(row.get("FORECAST CATEGORY") or "").strip()
        entry = {"ptype": _normalize_ptype(ptype_raw), "is_new": is_new}
        lookup[(row["OFFICE"], row["PROVIDER_NAME"])] = entry
        prov_fallback[row["PROVIDER_NAME"]] = entry
        if fcat == "FUTURE_START_ASSUMPTIONS_RAMP":
            future_start_offices.add(row["OFFICE"])

    _pmap_cache = (lookup, prov_fallback, future_start_offices)
    return _pmap_cache


def _normalize_ptype(raw):
    s = raw.strip().upper()
    if not s or s in ("NAN", "NONE", "OTHER", ""):
        return None
    if s == "GENERAL DENTIST":
        return "General Dentist"
    if s == "HYGIENIST":
        return "Hygienist"
    return raw.strip().title()


def _is_noise(name):
    n = str(name).lower()
    return any(p in n for p in config.NOISE_PATTERNS)


def _wd_cumulative(year, thru_month):
    """Working days for year 1..thru_month, respecting PARTIAL_MONTH config."""
    total = 0.0
    for m in range(1, thru_month + 1):
        if config.PARTIAL_MONTH and config.PARTIAL_MONTH[:2] == (m, year):
            total += config.PARTIAL_MONTH[2]
        else:
            total += config.WORKING_DAYS.get((m, year), 0.0)
    return total


def _yoy_pct(delta, baseline):
    """YoY % change of Rev/Day. Returns the string 'N/M' (Not Meaningful) when
    the 2025 baseline is negative, zero, or below the near-zero floor, where a
    percentage would be absurd; None when inputs are missing."""
    if delta is None or baseline is None:
        return None
    if baseline < config.NM_BASELINE_FLOOR:
        return "N/M"
    return delta / baseline * 100


def _build_checkpoints(rows_y1, rows_y2, include_levers=True):
    checkpoints = []
    for m in get_active_months():
        wd1 = _wd_cumulative(config.YEAR_1, m)
        wd2 = _wd_cumulative(config.YEAR_2, m)

        s1 = rows_y1[rows_y1["month_num"] <= m]
        s2 = rows_y2[rows_y2["month_num"] <= m]

        np1 = _safe(s1["NET PRODUCTION"].sum()) or 0.0
        np2 = _safe(s2["NET PRODUCTION"].sum()) or 0.0
        v1  = _safe(s1["VISITS"].sum()) or 0.0
        v2  = _safe(s2["VISITS"].sum()) or 0.0
        dd1 = _safe(s1["DOCTOR DAYS"].sum()) or 0.0
        dd2 = _safe(s2["DOCTOR DAYS"].sum()) or 0.0
        npc1 = _safe(s1["NEW PATIENT COUNT"].sum()) or 0.0
        npc2 = _safe(s2["NEW PATIENT COUNT"].sum()) or 0.0

        rd1  = np1 / wd1  if wd1  else None
        rd2  = np2 / wd2  if wd2  else None
        spv1 = np1 / v1   if v1 > 0 else None
        spv2 = np2 / v2   if v2 > 0 else None
        vdd1 = v1  / dd1  if dd1 > 0 else None
        vdd2 = v2  / dd2  if dd2 > 0 else None
        ddd1 = dd1 / wd1  if wd1  else None
        ddd2 = dd2 / wd2  if wd2  else None

        drd      = (rd2 - rd1)     if rd1 is not None and rd2 is not None else None
        drd_pct  = _yoy_pct(drd, rd1)
        dspv     = (spv2 - spv1)   if spv1 is not None and spv2 is not None else None
        dvdd     = (vdd2 - vdd1)   if vdd1 is not None and vdd2 is not None else None

        lev_spv = lev_vdd = lev_ddd = None
        pct_spv = pct_vdd = pct_ddd = None

        if include_levers and all(
            x is not None for x in [spv1, spv2, vdd1, vdd2, ddd1, ddd2, drd]
        ):
            lev_spv = (spv2 - spv1) * vdd1 * ddd1
            lev_vdd = spv2 * (vdd2 - vdd1) * ddd1
            lev_ddd = spv2 * vdd2 * (ddd2 - ddd1)
            if drd != 0:
                pct_spv = lev_spv / drd * 100
                pct_vdd = lev_vdd / drd * 100
                pct_ddd = lev_ddd / drd * 100

        checkpoints.append({
            "month_num": m,
            "label": MONTH_LABELS[m],
            "wd25": wd1,  "wd26": wd2,
            "v25":  v1,   "v26":  v2,
            "dd25": dd1,  "dd26": dd2,
            "rd25": rd1,  "rd26": rd2,  "drd": drd, "drd_pct": drd_pct,
            "spv25": spv1, "spv26": spv2, "dspv": dspv,
            "vdd25": vdd1, "vdd26": vdd2, "dvdd": dvdd,
            "ddd25": ddd1, "ddd26": ddd2,
            "np25": np1,  "np26": np2,  "dnp": np2 - np1,
            "npc25": npc1, "npc26": npc2, "dnpc": npc2 - npc1,
            "lev_spv": lev_spv, "lev_vdd": lev_vdd, "lev_ddd": lev_ddd,
            "pct_spv": pct_spv, "pct_vdd": pct_vdd, "pct_ddd": pct_ddd,
        })
    return checkpoints


def _compute_trend(checkpoints):
    baseline = None
    baseline_month = None
    for cp in checkpoints:
        if cp["drd"] is not None:
            baseline = cp["drd"]
            baseline_month = cp["label"]
            break

    last_cp = checkpoints[-1]
    if last_cp["drd"] is None or baseline is None:
        return None, baseline_month

    diff = last_cp["drd"] - baseline
    pct_chg = abs(diff / abs(baseline)) * 100 if baseline != 0 else (100.0 if diff else 0.0)

    if pct_chg < 5:
        return "stable", baseline_month
    return ("up" if diff > 0 else "down"), baseline_month


def get_qualifying_providers(office_detail_df):
    """Return ordered list of qualifying provider names for one office."""
    clean = office_detail_df[~office_detail_df["PROVIDER"].apply(_is_noise)]

    providers = {}
    for prov, grp in clean.groupby("PROVIDER"):
        np1 = _safe(grp[grp["year_num"] == config.YEAR_1]["NET PRODUCTION"].sum()) or 0.0
        np2 = _safe(grp[grp["year_num"] == config.YEAR_2]["NET PRODUCTION"].sum()) or 0.0
        pk  = max(np1, np2)
        if pk > 0:
            providers[prov] = {"np1": np1, "np2": np2, "pk": pk}

    if not providers:
        return []

    total = sum(v["pk"] for v in providers.values())
    sorted_provs = sorted(providers.items(), key=lambda x: -x[1]["pk"])

    qualifying = []
    cum = 0.0
    for name, data in sorted_provs:
        pct = data["pk"] / total * 100
        if pct >= config.PROVIDER_FLOOR_PCT:
            qualifying.append(name)
            cum += pct
            if cum >= config.PROVIDER_THRESHOLD_PCT:
                break
    return qualifying


def build_office_data():
    summary_df, _ = load_source_data()
    _, _, future_start_offices = load_provider_map()
    named = {o["name"] for o in config.OFFICE_LIST}
    result = []

    for od in config.OFFICE_LIST:
        rows = summary_df[summary_df["OFFICE"] == od["name"]]
        cps  = _build_checkpoints(
            rows[rows["year_num"] == config.YEAR_1],
            rows[rows["year_num"] == config.YEAR_2],
            include_levers=True,
        )
        trend, baseline_month = _compute_trend(cps)
        result.append({
            "name": od["name"],
            "state": od["state"],
            "rank": od["rank"],
            "is_other": False,
            "is_future_start": od["name"] in future_start_offices,
            "checkpoints": cps,
            "trend": trend,
            "trend_base": baseline_month,
        })

    # "Other (N offices)" rollup
    other = summary_df[~summary_df["OFFICE"].isin(named)]
    n_other = other["OFFICE"].nunique()
    cps = _build_checkpoints(
        other[other["year_num"] == config.YEAR_1],
        other[other["year_num"] == config.YEAR_2],
        include_levers=False,
    )
    result.append({
        "name": f"Other ({n_other} offices)",
        "state": None,
        "rank": None,
        "is_other": True,
        "checkpoints": cps,
        "trend": None,
        "trend_base": None,
    })

    return result


def _ds_metrics(rows, months=None):
    """Build the Data Summary 7-metric structure for one entity (office or
    provider), split by year. Monthly values are INDIVIDUAL-month actuals (not
    YTD-cumulative). Each metric array is length 6: the 5 months + YTD Total.

    Additive metrics (np, visits, drdays, newpat) → YTD is the sum of months.
    Ratio metrics (spv, vdd, rpd) → YTD is recomputed from the YTD totals, the
    correct production-weighted figure (summing monthly ratios is meaningless).
    """
    if months is None:
        months = get_active_months()
    def per_year(year):
        yr = rows[rows["year_num"] == year]
        npv, vv, ddv, npcv, spvv, vddv, rpdv = [], [], [], [], [], [], []
        for m in months:
            mr = yr[yr["month_num"] == m]
            np_  = _safe(mr["NET PRODUCTION"].sum()) or 0.0
            v_   = _safe(mr["VISITS"].sum()) or 0.0
            dd_  = _safe(mr["DOCTOR DAYS"].sum()) or 0.0
            npc_ = _safe(mr["NEW PATIENT COUNT"].sum()) or 0.0
            wd   = config.WORKING_DAYS.get((m, year), 0.0)
            npv.append(np_);  vv.append(v_);  ddv.append(dd_);  npcv.append(npc_)
            spvv.append(np_ / v_  if v_  > 0 else None)
            vddv.append(v_  / dd_ if dd_ > 0 else None)
            rpdv.append(np_ / wd  if wd       else None)

        np_t  = sum(npv);  v_t = sum(vv);  dd_t = sum(ddv);  npc_t = sum(npcv)
        wd_t  = sum(config.WORKING_DAYS.get((m, year), 0.0) for m in months)
        return {
            "np":     npv  + [np_t],
            "visits": vv   + [v_t],
            "drdays": ddv  + [dd_t],
            "newpat": npcv + [npc_t],
            "spv":    spvv + [np_t / v_t  if v_t  > 0 else None],
            "vdd":    vddv + [v_t  / dd_t if dd_t > 0 else None],
            "rpd":    rpdv + [np_t / wd_t if wd_t      else None],
        }
    return {"y1": per_year(config.YEAR_1), "y2": per_year(config.YEAR_2)}


def build_data_summary():
    """Per-office and per-named-provider monthly actuals — the 'show your work'
    source-data view (Data Summary tab). Office totals from SUMMARY rows,
    provider breakdown from DETAIL rows, named providers via the same 90%/2%
    qualifying filter as the Provider Deep Dive tab. Both qualification and the
    metric arrays span the full active window (get_active_months)."""
    summary_df, detail_df = load_source_data()
    result = []

    for od in config.OFFICE_LIST:
        oname = od["name"]
        orows = summary_df[summary_df["OFFICE"] == oname]
        prows_all = detail_df[detail_df["OFFICE"] == oname]

        providers = []
        for pname in get_qualifying_providers(prows_all):
            prows = prows_all[prows_all["PROVIDER"] == pname]
            providers.append({"name": pname, "metrics": _ds_metrics(prows)})

        result.append({
            "office":    oname,
            "state":     od["state"],
            "metrics":   _ds_metrics(orows),
            "providers": providers,
        })

    return result


def build_provider_data():
    _, detail_df = load_source_data()
    pmap, pfallback, _ = load_provider_map()
    result = []

    for od in config.OFFICE_LIST:
        oname = od["name"]
        orows = detail_df[detail_df["OFFICE"] == oname]
        qualifying = get_qualifying_providers(orows)
        qset = set(qualifying)
        providers = []

        for pname in qualifying:
            prows = orows[orows["PROVIDER"] == pname]
            cps   = _build_checkpoints(
                prows[prows["year_num"] == config.YEAR_1],
                prows[prows["year_num"] == config.YEAR_2],
                include_levers=True,
            )
            trend, baseline_month = _compute_trend(cps)
            entry = pmap.get((oname, pname)) or pfallback.get(pname, {})
            providers.append({
                "name":     pname,
                "ptype":    entry.get("ptype"),
                "is_new":   entry.get("is_new", False),
                "is_other": False,
                "checkpoints": cps,
                "trend":    trend,
                "trend_base": baseline_month,
            })

        # Other providers rollup
        other_rows = orows[~orows["PROVIDER"].isin(qset)]
        n_other    = other_rows["PROVIDER"].nunique()
        cps_other  = _build_checkpoints(
            other_rows[other_rows["year_num"] == config.YEAR_1],
            other_rows[other_rows["year_num"] == config.YEAR_2],
            include_levers=False,
        )
        providers.append({
            "name":     f"Other ({n_other} providers)",
            "ptype":    None,
            "is_new":   False,
            "is_other": True,
            "n_other":  n_other,
            "checkpoints": cps_other,
            "trend":    None,
            "trend_base": None,
        })

        result.append({
            "office":    oname,
            "state":     od["state"],
            "providers": providers,
        })

    return result

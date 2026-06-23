import json
import config
import pipeline
from mix_dollars import (realization_diagnostic, tag_for, monthly_realization_trend,
                         monthly_realization_by_office)

# ── View 1: Realization Diagnostic — (label, css, plain-language tooltip) per driver ──
_RZ_TAG = {
    "collecting": ("Collecting less", "rz-bad",
                   "Net/proc fell because the write-off rate rose (gross held) — a collections problem."),
    "billing":    ("Billing less", "rz-warn",
                   "Net/proc fell because gross/proc dropped — a pricing/fee problem."),
    "both":       ("Both", "rz-bad",
                   "Gross softened AND the write-off rate rose."),
    "mix":        ("Mixed", "rz-mut",
                   "Net/proc moved without a single clear write-off-rate or gross driver."),
    "masked":     ("Realization &darr; &mdash; masked by gross", "rz-warn",
                   "The write-off rate rose, but net/proc only held because gross rose to cover it — deterioration hidden by a fee increase."),
    "up":         ("Realization held", "rz-good",
                   "Write-off rate flat or improved."),
}


def _rz_pct(x, dec=1):
    return "&mdash;" if x is None else f"{x*100:.{dec}f}%"


def _rz_ppt(x, dec=1):
    return "&mdash;" if x is None else f"{x*100:+.{dec}f} pt"


def _rz_money(x):
    return "&mdash;" if x is None else f"${x:,.0f}"


def _rz_dmoney(x):
    return "&mdash;" if x is None else f"{'+' if x >= 0 else '&minus;'}${abs(x):,.0f}"


def _rz_km(x):
    """Compact dollars for the totals table: $3.66M / $798K / $420."""
    if x is None:
        return "&mdash;"
    ax = abs(x)
    if ax >= 1e6:
        return f"${ax/1e6:.2f}M"
    if ax >= 1e3:
        return f"${ax/1e3:.0f}K"
    return f"${ax:,.0f}"


def _rz_dkm(x):
    """Signed compact dollars (YoY deltas): +$316K / &minus;$107K."""
    return "&mdash;" if x is None else (("+" if x >= 0 else "&minus;") + _rz_km(abs(x)))


def _realization_card(diag, scope_label, monthly_t):
    """Render one realization card (company OR one office) from a realization_diagnostic
    payload. Per-procedure basis; side-by-side 2025 | 2026 | Δ for each metric; the shaded
    write-off hero is dollar-led ($/proc written off, 2026 emphasized, rate beneath, pt Δ
    in its own column). Honest blanks for thin (office,group) cells; legitimately-negative
    office rates (net credits > write-offs) shown as-is with a † note. Lead + KPIs are
    entity-aware so an office never inherits the company's qualitative claims. Each row is
    click-to-explode into its monthly Net/proc trend (monthly_t is THIS scope's series, so
    the explode re-scopes with the office slicer)."""
    h = diag["headline"]
    y1, y2 = diag["meta"]["year_1"], diag["meta"]["year_2"]

    def _g(gp, c):
        return (gp * c) if (gp is not None and c) else 0.0

    def _arrow(v):
        return "&#9650;" if (v and v > 0) else ("&#9660;" if (v and v < 0) else "")

    # honest-blank: drop procedures with no activity in EITHER year; SORT by size (gross $)
    rows_live = [r for r in diag["rows"] if (r["count25"] or 0) > 0 or (r["count26"] or 0) > 0]
    items = sorted(({**r, "g26": _g(r["gross_per26"], r["count26"])} for r in rows_live),
                   key=lambda x: x["g26"], reverse=True)

    has_credit = [False]

    def wo_cell(wo, gp, big):
        """$/proc written off (= rate × gross/proc), with the rate beneath. Big = 2026."""
        wod = (wo * gp) if (wo is not None and gp is not None) else None
        acls = "rz-wo-amt" if big else "rz-wo-amt2"
        if wod is None:
            return f'<div class="{acls}">&mdash;</div><div class="rz-wo-rate">&mdash;</div>'
        if wod < 0:   # net credits exceeded write-offs (small office denominator) — real, not a bug
            has_credit[0] = True
            mark = ('<span class="rz-cr" title="Net credits / adjustments exceeded write-offs here '
                    '&mdash; a real net positive on a small office denominator, not a write-off or a bug.">&dagger;</span>')
            return (f'<div class="{acls} rz-credit">&minus;${abs(wod):,.0f}{mark}</div>'
                    f'<div class="rz-wo-rate rz-credit">{_rz_pct(wo)}</div>')
        return f'<div class="{acls}">{_rz_money(wod)}</div><div class="rz-wo-rate">{_rz_pct(wo)}</div>'

    trs = []
    for x in items:
        label, cls, tip = _RZ_TAG.get(x["tag"], ("&mdash;", "rz-mut", ""))
        dwo, dgp, dnp = x["d_wo"], x["d_gross_per"], x["d_net_per"]
        rate_cls = "nc" if (dwo and dwo > 0) else ("pc" if (dwo and dwo < 0) else "")
        dgp_cls = "pc" if (dgp and dgp > 0) else ("nc" if (dgp and dgp < 0) else "")
        dnp_cls = "pc" if (dnp and dnp > 0) else ("nc" if (dnp and dnp < 0) else "")
        scale = f'{int(x["count26"] or 0):,} procs &middot; {_rz_km(x["net26"])} net'
        trs.append(
            '<tr class="rz-row" onclick="rzToggle(this)">'
            f'<td class="l"><span class="rz-caret">&#9654;</span>{x["group"]}<div class="rz-sub rz-size">{scale}</div></td>'
            f'<td>{_rz_money(x["gross_per25"])}</td><td>{_rz_money(x["gross_per26"])}</td>'
            f'<td class="{dgp_cls}">{_rz_dmoney(dgp)}</td>'
            f'<td class="rz-hero">{wo_cell(x["wo25"], x["gross_per25"], False)}</td>'
            f'<td class="rz-hero rz-hero26">{wo_cell(x["wo26"], x["gross_per26"], True)}</td>'
            f'<td class="rz-hero {rate_cls}"><b>{_arrow(dwo)} {_rz_ppt(dwo)}</b></td>'
            f'<td>{_rz_money(x["net_per25"])}</td><td>{_rz_money(x["net_per26"])}</td>'
            f'<td class="{dnp_cls}">{_rz_dmoney(dnp)}</td>'
            f'<td><span class="rz-tag {cls}" title="{tip}">{label}</span></td>'
            '</tr>'
            f'<tr class="rz-exp" style="display:none"><td colspan="11">{_rz_net_explode(monthly_t, x["group"])}</td></tr>'
        )

    # entity-aware "control": did gross/proc hold? (majority of live procedures rose)
    deltas = [r["d_gross_per"] for r in rows_live if r["d_gross_per"] is not None]
    n_up = sum(1 for v in deltas if v > 0)
    n_tot = len(deltas)
    gross_held = n_tot > 0 and n_up * 2 >= n_tot
    tail = (" &mdash; while gross-per-procedure held or rose. The net decline is <b>collection, not price</b>."
            if gross_held else
            " &mdash; and gross-per-procedure also softened, so both collection and billing are in play.")

    dpts = h["d_pts"]
    if dpts is None:
        lead = f"Not enough closed data to summarize realization {scope_label}."
    elif h["wo26"] is not None and h["wo26"] < 0:
        # net-credit scope (credits/adjustments exceeded write-offs) — honest, not a bug
        lead = (f"Net credits and adjustments <b>exceeded</b> write-offs {scope_label} "
                f"(a net <b class=\"pc\">{abs(h['wo26'])*100:.1f}%</b> positive on a small denominator) "
                f"&mdash; realization isn't the concern at this scope; read individual procedures below.")
    elif dpts > 0.0005:
        lead = (f"Realization is eroding {scope_label}. We wrote off <b>{_rz_pct(h['wo25'])}</b> of gross "
                f"production in {y1} and <b>{_rz_pct(h['wo26'])}</b> in {y2} &mdash; "
                f"<b class=\"nc\">{dpts*100:+.1f} points</b> more{tail}")
    elif dpts < -0.0005:
        lead = (f"Realization <b>improved</b> {scope_label}. We wrote off <b>{_rz_pct(h['wo25'])}</b> of gross "
                f"production in {y1} and <b>{_rz_pct(h['wo26'])}</b> in {y2} &mdash; "
                f"<b class=\"pc\">{abs(dpts)*100:.1f} points</b> less.")
    else:
        lead = (f"Realization held roughly flat {scope_label} &mdash; <b>{_rz_pct(h['wo25'])}</b> in {y1} "
                f"vs <b>{_rz_pct(h['wo26'])}</b> in {y2}.{tail}")

    dpts_cls = "" if dpts is None else ("neg" if dpts > 0 else "pos")
    held_cls, held_word = ("pos", "Held") if gross_held else ("neg", "Softened")
    credit_note = ('<div class="rz-foot">&dagger; a negative write-off = net credits / adjustments exceeded '
                   'write-offs (small office denominators) &mdash; a real net positive, not a bug.</div>'
                   if has_credit[0] else '')

    return f"""
  <div class="card realz-card">
    <div class="section-lbl">Realization &mdash; what we bill vs. what we keep (gross &rarr; write-offs &rarr; net, by procedure)</div>
    <div class="rz-lead-stmt">{lead}</div>
    <div class="rz-def"><b>What is realization?</b> The share of what you bill (gross) that you keep (net),
      after insurance write-offs and adjustments. Write-off rate = Adjustments &divide; Gross. When it rises,
      you're doing the same work and keeping less &mdash; a collections problem, not a fee or volume one.</div>
    <div class="rz-kpis">
      <div class="kpi"><div class="kpi-lbl">% written off &mdash; {y1}</div><div class="kpi-val">{_rz_pct(h['wo25'])}</div><div class="rz-ksub">Adj &divide; Gross</div></div>
      <div class="kpi"><div class="kpi-lbl">% written off &mdash; {y2}</div><div class="kpi-val">{_rz_pct(h['wo26'])}</div><div class="rz-ksub">Adj &divide; Gross</div></div>
      <div class="kpi"><div class="kpi-lbl">&Delta; realization</div><div class="kpi-val {dpts_cls}">{_rz_ppt(dpts)}</div><div class="rz-ksub">more written off = worse</div></div>
      <div class="kpi"><div class="kpi-lbl">Gross/proc (control)</div><div class="kpi-val {held_cls}">{held_word}</div><div class="rz-ksub">{n_up}/{n_tot} procs&rsquo; gross/proc rose</div></div>
    </div>
    <div class="rz-nav">(This is the $/Visit half of the Rev/Day decline &mdash; see Office Analysis for the lever breakdown.)</div>
    <div class="hint">Sorted by <b>procedure size</b> (total gross). Each metric shows <b>2025, 2026 and the change</b> side by side. Columns flow <b>gross/proc &rarr; write-off/proc &rarr; net/proc</b> (per procedure, volume removed). The shaded write-off column is <b>dollar-led</b> &mdash; $ written off per procedure (2026 emphasized), the rate (% of gross) beneath, and the YoY point change in its &Delta; column.</div>
    <table class="rz-tbl">
      <thead>
        <tr><th class="l" rowspan="2">Procedure<div class="rz-h2">&amp; scale (procs &middot; net)</div></th>
          <th colspan="3">Gross / proc</th>
          <th class="rz-hero" colspan="3">Write-off / proc &mdash; lost<div class="rz-h2">$ per proc &middot; % of gross</div></th>
          <th colspan="3">Net / proc</th>
          <th rowspan="2">Driver</th></tr>
        <tr><th>{y1}</th><th>{y2}</th><th>&Delta;</th>
          <th class="rz-hero">{y1}</th><th class="rz-hero rz-hero26">{y2}</th><th class="rz-hero">&Delta; pt</th>
          <th>{y1}</th><th>{y2}</th><th>&Delta;</th></tr>
      </thead>
      <tbody>{''.join(trs)}</tbody>
    </table>
    {credit_note}
    <div class="rz-legend">
      <span><b>Collecting less</b> &mdash; net/proc fell because the write-off rate rose (gross held): a collections problem.</span>
      <span><b>Billing less</b> &mdash; net/proc fell because gross/proc dropped: a pricing/fee problem.</span>
      <span><b>Both</b> &mdash; gross softened AND the write-off rate rose.</span>
      <span><b>Realization &darr; masked by gross</b> &mdash; the write-off rate rose, but net/proc only held because gross rose to cover it (deterioration hidden by a fee increase).</span>
      <span><b>Realization held</b> &mdash; write-off rate flat or improved.</span>
    </div>
  </div>"""


# ── View 1 — MONTHLY realization trend (write-off-rate shape, 2025 vs 2026) ───
_RZ_C25, _RZ_C26 = "#9aa6b8", "#C0392B"   # 2025 grey, 2026 house-red


def _rz_trend_svg(t):
    """Company write-off-rate line chart: 2025 vs 2026 over the active window, with the
    YoY gap shaded and the MTD month drawn provisional. Pure inline SVG (no JS/deps)."""
    months = t["meta"]["active_months"]
    mtd = t["meta"]["mtd_month"]
    closed = [m for m in months if m != mtd]
    lab = t["meta"]["month_labels"]
    y1 = {r["month"]: r["wo"] for r in t["y1"]}
    y2 = {r["month"]: r["wo"] for r in t["y2"]}
    vals = [v for v in list(y1.values()) + list(y2.values()) if v is not None]
    if not vals:
        return '<div class="rzm-nodata">No monthly write-off data at this scope.</div>'
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.18 or 0.01
    ymin, ymax = lo - pad, hi + pad
    W, H = 820, 300
    L, R, T, B = 52, 116, 18, 38
    pw, ph = W - L - R, H - T - B
    n = len(months)
    xs = {m: L + (i / (n - 1)) * pw for i, m in enumerate(months)}

    def Y(v):
        return T + (ymax - v) / (ymax - ymin) * ph

    grid = []
    step = 0.02
    g = int(ymin / step) * step
    while g <= ymax + 1e-9:
        if g >= ymin:
            yy = Y(g)
            grid.append(f'<line x1="{L}" y1="{yy:.1f}" x2="{L+pw}" y2="{yy:.1f}" class="grid"/>'
                        f'<text x="{L-8}" y="{yy+3:.1f}" class="ylab">{g*100:.0f}%</text>')
        g += step

    band = ""
    if mtd in xs:
        bx = (xs[closed[-1]] + xs[mtd]) / 2
        band = (f'<rect x="{bx:.1f}" y="{T}" width="{L+pw-bx:.1f}" height="{ph}" class="provband"/>'
                f'<text x="{(bx+L+pw)/2:.1f}" y="{T+11}" class="provlab">MTD &middot; provisional</text>')

    def poly(series, color, dashed_tail):
        pts_closed = [(xs[m], Y(series[m])) for m in closed if series.get(m) is not None]
        line = ('<polyline class="ln" points="'
                + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts_closed) + f'" stroke="{color}"/>')
        tail = ""
        if dashed_tail and mtd in xs and series.get(mtd) is not None and series.get(closed[-1]) is not None:
            x0, y0 = xs[closed[-1]], Y(series[closed[-1]])
            x1, y1v = xs[mtd], Y(series[mtd])
            tail = (f'<line class="lndash" x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1v:.1f}" stroke="{color}"/>'
                    f'<circle cx="{x1:.1f}" cy="{y1v:.1f}" r="3.2" fill="#fff" stroke="{color}" stroke-dasharray="2 1.5"/>')
        dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{color}"/>' for x, y in pts_closed)
        return line + tail + dots

    cl = [m for m in closed if y1.get(m) is not None and y2.get(m) is not None]
    gap = ""
    if len(cl) >= 2:
        top = [(xs[m], Y(y2[m])) for m in cl]
        bot = [(xs[m], Y(y1[m])) for m in reversed(cl)]
        gap = ('<polygon class="gap" points="'
               + " ".join(f"{x:.1f},{y:.1f}" for x, y in top + bot) + '"/>')

    xlabels = "".join(
        f'<text x="{xs[m]:.1f}" y="{H-B+18}" class="xlab">{lab[m]}</text>' for m in months)
    lm = closed[-1]
    endlbl = ""
    for series, color, nm in ((y2, _RZ_C26, str(t['meta']['year_2'])),
                              (y1, _RZ_C25, str(t['meta']['year_1']))):
        if series.get(lm) is not None:
            endlbl += (f'<text x="{xs[lm]+8:.1f}" y="{Y(series[lm])+3:.1f}" class="endlab" '
                       f'fill="{color}">{nm} &middot; {series[lm]*100:.1f}%</text>')
    return (f'<svg viewBox="0 0 {W} {H}" class="trend" role="img" '
            f'aria-label="Monthly write-off rate, {t["meta"]["year_1"]} vs {t["meta"]["year_2"]}">'
            + "".join(grid) + band + gap
            + poly(y1, _RZ_C25, True) + poly(y2, _RZ_C26, True)
            + xlabels + endlbl + "</svg>")


def _rz_spark(g, t):
    """Tiny per-procedure 2025-vs-2026 write-off sparkline over closed months."""
    closed = [m for m in t["meta"]["active_months"] if m != t["meta"]["mtd_month"]]
    y1 = {r["month"]: r["per_group"][g]["wo"] for r in t["y1"]}
    y2 = {r["month"]: r["per_group"][g]["wo"] for r in t["y2"]}
    vals = [v for v in list(y1.values()) + list(y2.values()) if v is not None]
    if len([m for m in closed if y2.get(m) is not None]) < 3:
        return None
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    w, h = 104, 30
    n = len(closed)
    xs = {m: 2 + (i / (n - 1)) * (w - 4) for i, m in enumerate(closed)}

    def Y(v):
        return 3 + (hi - v) / rng * (h - 6)

    def pl(series, color):
        pts = [(xs[m], Y(series[m])) for m in closed if series.get(m) is not None]
        if len(pts) < 2:
            return ""
        return (f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x,y in pts)}" '
                f'fill="none" stroke="{color}" stroke-width="1.4"/>')
    return (f'<svg viewBox="0 0 {w} {h}" class="spark">' + pl(y1, _RZ_C25) + pl(y2, _RZ_C26) + "</svg>")


def _rz_net_explode(t, group):
    """Hidden explode for one procedure row: that procedure's NET / procedure by month,
    2025 vs 2026, mirroring the write-off trend's visual language (months X, two-year
    compare, June dashed/flagged MTD) + a compact Net/proc 25 | 26 | Δ strip. `t` is the
    CURRENT scope's monthly series (company or the selected office) — so the explode
    re-scopes with the slicer. Thin discipline: a month plots only with >=3 procedures
    that month; a year's line draws only with >=2 plottable closed months; otherwise an
    honest text-blank (no jumpy line on 1-2 procedures/month)."""
    MIN = 3
    mths = t["meta"]["active_months"]
    mtd = t["meta"]["mtd_month"]
    closed = [m for m in mths if m != mtd]
    lab = t["meta"]["month_labels"]
    y1y, y2y = t["meta"]["year_1"], t["meta"]["year_2"]
    c25 = {r["month"]: r["per_group"][group] for r in t["y1"]}
    c26 = {r["month"]: r["per_group"][group] for r in t["y2"]}

    def npv(c, m):
        return c[m]["net_per"] if (c[m]["count"] or 0) >= MIN else None
    y1 = {m: npv(c25, m) for m in mths}
    y2 = {m: npv(c26, m) for m in mths}
    p1 = [m for m in closed if y1[m] is not None]
    p2 = [m for m in closed if y2[m] is not None]
    if len(p1) < 2 and len(p2) < 2:
        return ('<div class="rz-exp-h">Net / procedure by month</div>'
                f'<div class="rz-exp-note">Too thin to chart at this scope &mdash; under {MIN} '
                f'{group} procedures per month, so a monthly Net/proc line would be noise, not signal.</div>')

    vals = [v for v in list(y1.values()) + list(y2.values()) if v is not None]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.22 or max(hi * 0.04, 1.0)
    ymin, ymax = lo - pad, hi + pad
    W, H = 720, 200
    L, R, T, B = 60, 92, 14, 28
    pw, ph = W - L - R, H - T - B
    n = len(mths)
    xs = {m: L + (i / (n - 1)) * pw for i, m in enumerate(mths)}

    def Y(v):
        return T + (ymax - v) / (ymax - ymin) * ph

    grid = []
    for i in range(4):
        gv = ymin + i * (ymax - ymin) / 3
        yy = Y(gv)
        grid.append(f'<line x1="{L}" y1="{yy:.1f}" x2="{L+pw}" y2="{yy:.1f}" class="grid"/>'
                    f'<text x="{L-6}" y="{yy+3:.1f}" class="ylab">${gv:,.0f}</text>')

    band = ""
    if mtd in xs:
        bx = (xs[closed[-1]] + xs[mtd]) / 2
        band = (f'<rect x="{bx:.1f}" y="{T}" width="{L+pw-bx:.1f}" height="{ph}" class="provband"/>'
                f'<text x="{(bx+L+pw)/2:.1f}" y="{T+10}" class="provlab">{lab[mtd]} MTD</text>')

    def poly(series, color):
        pts = [(xs[m], Y(series[m])) for m in closed if series[m] is not None]
        line = ('<polyline class="ln" points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                + f'" stroke="{color}"/>') if len(pts) >= 2 else ""
        tail = ""
        if mtd in xs and series[mtd] is not None and series[closed[-1]] is not None:
            x0, y0 = xs[closed[-1]], Y(series[closed[-1]])
            x1, y1v = xs[mtd], Y(series[mtd])
            tail = (f'<line class="lndash" x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1v:.1f}" stroke="{color}"/>'
                    f'<circle cx="{x1:.1f}" cy="{y1v:.1f}" r="3" fill="#fff" stroke="{color}"/>')
        dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{color}"/>' for x, y in pts)
        return line + tail + dots

    clb = [m for m in closed if y1[m] is not None and y2[m] is not None]
    gap = ""
    if len(clb) >= 2:
        top = [(xs[m], Y(y2[m])) for m in clb]
        bot = [(xs[m], Y(y1[m])) for m in reversed(clb)]
        gap = '<polygon class="gap" points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in top + bot) + '"/>'

    xlabels = "".join(f'<text x="{xs[m]:.1f}" y="{H-B+16}" class="xlab">{lab[m]}</text>' for m in mths)
    lm = p2[-1] if p2 else p1[-1]
    endlbl = ""
    for series, color, nm in ((y2, _RZ_C26, str(y2y)), (y1, _RZ_C25, str(y1y))):
        if series.get(lm) is not None:
            endlbl += (f'<text x="{xs[lm]+7:.1f}" y="{Y(series[lm])+3:.1f}" class="endlab" '
                       f'fill="{color}">{nm} ${series[lm]:,.0f}</text>')
    svg = (f'<svg viewBox="0 0 {W} {H}" class="rzx" role="img" '
           f'aria-label="{group} net per procedure by month, {y1y} vs {y2y}">'
           + "".join(grid) + band + gap + poly(y1, _RZ_C25) + poly(y2, _RZ_C26)
           + xlabels + endlbl + "</svg>")

    def _m(v):
        return "&mdash;" if v is None else f"${v:,.0f}"

    def _pc(m):
        return ' class="prov"' if m == mtd else ''
    head = "".join(f'<th{_pc(m)}>{lab[m]}</th>' for m in mths)
    r25 = "".join(f'<td{_pc(m)}>{_m(y1[m])}</td>' for m in mths)
    r26 = "".join(f'<td{_pc(m)}>{_m(y2[m])}</td>' for m in mths)

    def dcell(m):
        a, b = y1[m], y2[m]
        d = None if (a is None or b is None) else (b - a)
        base = "nc" if (d is not None and d < 0) else ("pc" if (d is not None and d > 0) else "")
        cls = (("prov " + base).strip()) if m == mtd else base
        txt = "&mdash;" if d is None else (("&minus;$" + f"{abs(d):,.0f}") if d < 0 else f"+${d:,.0f}")
        return f'<td class="{cls}">{txt}</td>'
    rdd = "".join(dcell(m) for m in mths)

    table = (f'<table class="rzx-tbl"><thead><tr><th class="l">Net/proc</th>{head}</tr></thead>'
             f'<tbody><tr><td class="l">{y1y}</td>{r25}</tr>'
             f'<tr><td class="l">{y2y}</td>{r26}</tr>'
             f'<tr><td class="l">&Delta;</td>{rdd}</tr></tbody></table>')

    return (f'<div class="rz-exp-h">{group} &mdash; Net / procedure by month '
            f'(<span style="color:{_RZ_C26}">{y2y}</span> vs <span style="color:{_RZ_C25}">{y1y}</span>; '
            f'{lab[closed[0]]}&ndash;{lab[closed[-1]]} matched, {lab[mtd]} MTD/provisional)</div>'
            f'<div class="rzx-wrap">{svg}</div>{table}')


def _rz_monthly_card(t):
    """Monthly write-off-rate trend card: lead chart + computed timing callout + a
    HORIZONTAL monthly table (months across, metrics down — parallels the chart and fills
    the width) + secondary per-procedure sparklines. Sparse-office safe."""
    mths = t["meta"]["active_months"]
    mtd = t["meta"]["mtd_month"]
    closed = [m for m in mths if m != mtd]
    lab = t["meta"]["month_labels"]
    c25 = {r["month"]: r for r in t["y1"]}
    c26 = {r["month"]: r for r in t["y2"]}
    y1y, y2y = t["meta"]["year_1"], t["meta"]["year_2"]

    # timing read, computed (not hardcoded): steady / accelerating / recent / thin?
    gaps = [(c26[m]["wo"] - c25[m]["wo"]) for m in closed
            if c25[m]["wo"] is not None and c26[m]["wo"] is not None]
    if not gaps:
        read = "too little paired monthly data at this scope to call the shape"
    else:
        first_g, last_g, min_g = gaps[0], gaps[-1], min(gaps)
        worst26_m = max((m for m in closed if c26[m]["wo"] is not None),
                        key=lambda m: c26[m]["wo"], default=closed[-1])
        steady = min_g > 0.005
        accel = last_g > first_g + 0.005
        read = ("a <b>steady, structural gap</b> &mdash; 2026 runs above 2025 in "
                "<b>every</b> month from January, not a recent onset"
                if steady else "an <b>intermittent</b> gap") + (
                f", and it <b>widens late</b> ({first_g*100:+.1f}pt in {lab[closed[0]]} &rarr; "
                f"{last_g*100:+.1f}pt by {lab[closed[-1]]}, worst in {lab[worst26_m]} at "
                f"{c26[worst26_m]['wo']*100:.1f}%)" if accel else
                f", roughly flat across the window (~{sum(gaps)/len(gaps)*100:+.1f}pt)")

    # HORIZONTAL table: months across the top, metric rows down the side.
    def _pcls(m):
        return ' class="prov"' if m == mtd else ''
    head = ''.join(f'<th{_pcls(m)}>{lab[m]}{" (MTD)" if m == mtd else ""}</th>' for m in mths)

    def cellrow(fn):
        return ''.join(f'<td{_pcls(m)}>{fn(m)}</td>' for m in mths)

    def dcell(m):
        wo1, wo2 = c25[m]["wo"], c26[m]["wo"]
        dg = None if (wo1 is None or wo2 is None) else (wo2 - wo1)
        cls = "nc" if (dg and dg > 0) else ("pc" if (dg and dg < 0) else "")
        pc = ("prov " + cls).strip() if m == mtd else cls
        return f'<td class="{pc}"><b>{_rz_ppt(dg)}</b></td>'

    row_wo25 = cellrow(lambda m: _rz_pct(c25[m]["wo"]))
    row_wo26 = cellrow(lambda m: _rz_pct(c26[m]["wo"]))
    row_dpt = ''.join(dcell(m) for m in mths)
    row_gross = cellrow(lambda m: f'${c26[m]["gross"]:,.0f}')
    row_net = cellrow(lambda m: f'${c26[m]["net"]:,.0f}')

    sparks = []
    for g in t["meta"]["groups"]:
        s = _rz_spark(g, t)
        if s:
            sparks.append(f'<div class="sk"><div class="sk-l">{g}</div>{s}</div>')

    return f"""<div class="card realz-monthly-card">
    <div class="section-lbl">Is it steady, accelerating, or recent? &mdash; Monthly write-off-rate trend</div>
    <div class="hint">Same population and corrected basis as the view above &mdash; read as a <b>shape</b>.
      Company/office total only (procedure-level offered below; <b>provider</b>-monthly deliberately excluded
      as too noisy on small per-month counts). Closed {lab[closed[0]]}&ndash;{lab[closed[-1]]} is the read; {lab[mtd]} is MTD/provisional.</div>
    <div class="rzm-callout">The monthly shape shows {read}.</div>
    <div class="rzm-wrap">{_rz_trend_svg(t)}
      <div class="rzm-key">
        <span><i style="background:{_RZ_C26}"></i>{y2y}</span>
        <span><i style="background:{_RZ_C25}"></i>{y1y}</span>
        <span><i class="gapkey"></i>YoY gap (2026 excess written off)</span>
      </div>
    </div>
    <table class="rzm-tbl rzm-h">
      <thead><tr><th class="l">Metric</th>{head}</tr></thead>
      <tbody>
        <tr><td class="l">% WO {y1y}</td>{row_wo25}</tr>
        <tr><td class="l">% WO {y2y}</td>{row_wo26}</tr>
        <tr><td class="l">&Delta; pt</td>{row_dpt}</tr>
        <tr class="ctxrow"><td class="l">Gross $ {y2y}</td>{row_gross}</tr>
        <tr class="ctxrow"><td class="l">Net $ {y2y}</td>{row_net}</tr>
      </tbody>
    </table>
    <div class="sk-head">Per procedure &mdash; write-off shape (secondary; <span style="color:{_RZ_C26}">{y2y}</span> vs <span style="color:{_RZ_C25}">{y1y}</span>, {lab[closed[0]]}&ndash;{lab[closed[-1]]})</div>
    <div class="sk-grid">{''.join(sparks)}</div>
  </div>"""


def _realization_navtab(dollar_dataset):
    """The Realization nav-tab button — absent (so the tab bar is unchanged) when there
    is no dollar dataset to render."""
    if dollar_dataset is None:
        return ""
    return '\n  <button class="nav-tab" id="navTab6" onclick="switchTab(6)">&#128181; Realization</button>'


def _rz_esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _realization_tab(dollar_dataset):
    """The full Realization tab with an OFFICE SLICER. Pre-renders the company view
    (default, the headline) plus every office into hidden panes; the slicer JS toggles
    which pane is visible, so the table + KPI band + intro + monthly trend all switch
    together. Company uses company_rendered (ties to the headline); offices use
    office_rollup + a single-pass monthly aggregation (no per-office reload). No provider
    slicer by design. Returns '' when no dollar dataset (tab cleanly absent)."""
    if dollar_dataset is None:
        return ""
    monthly = monthly_realization_by_office()          # ONE pass: company + all offices

    panes, options = [], []
    comp_t = monthly["__company__"]
    comp = _realization_card(realization_diagnostic(dollar_dataset), "company-wide", comp_t)
    panes.append(f'<div class="realz-pane" id="rzpane-0">{comp}\n  {_rz_monthly_card(comp_t)}\n  </div>')
    options.append('<option value="0">All offices (company)</option>')

    for i, o in enumerate(sorted(dollar_dataset["office_rollup"], key=lambda x: x["office"]), start=1):
        name = o["office"]
        diag = realization_diagnostic(entity=o["groups"], scope="office · " + name)
        office_t = monthly.get(name, monthly["__company__"])
        card = _realization_card(diag, f"at <b>{_rz_esc(name)}</b>", office_t)
        mcard = _rz_monthly_card(office_t)
        panes.append(f'<div class="realz-pane" id="rzpane-{i}" style="display:none">{card}\n  {mcard}\n  </div>')
        options.append(f'<option value="{i}">{_rz_esc(name)}</option>')

    slicer = (
        '<div class="card realz-slicer">'
        '<label for="realzOffice">Scope:</label>'
        f'<select id="realzOffice" onchange="realzPick(this.value)">{"".join(options)}</select>'
        '<span class="realz-slicer-note">Company is the headline; office is an opt-in drill '
        '&mdash; no provider level (too noisy on small denominators).</span></div>')

    return ('<!-- ═══════════════════════════════════════════════════\n'
            '     TAB 6 — REALIZATION (procedure $ / write-off diagnostic; office slicer)\n'
            '════════════════════════════════════════════════════ -->\n'
            f'<div id="tab6" style="display:none">{slicer}\n{"".join(panes)}</div>\n')


# ── View 2: per-provider procedure-dollar detail (Mix Shift expand) ───────────
def _mix_dollars_payload(dollar_dataset):
    """Compact per-(office, provider, group) dollar lookup for the Mix Shift expand.
    Nested {office:{provider:{group:{...}}}} so provider/office names need no delimiter.
    Closed (matched Jan–May) window, corrected basis. Groups with no procedures in
    either year are omitted. Returns {} when no dataset (keeps payload absent)."""
    if dollar_dataset is None:
        return {}
    out = {}
    for p in dollar_dataset["providers"]:
        g_out = {}
        for g in dollar_dataset["meta"]["groups"]:
            a = p["groups"]["y1"]["closed"][g]
            b = p["groups"]["y2"]["closed"][g]
            if (a["count"] or 0) <= 0 and (b["count"] or 0) <= 0:
                continue
            wo1 = None if a["adj_rate"] is None else -a["adj_rate"]
            wo2 = None if b["adj_rate"] is None else -b["adj_rate"]
            dwo = None if (wo1 is None or wo2 is None) else wo2 - wo1
            np1, np2 = a["net_per"], b["net_per"]
            gp1, gp2 = a["gross_per"], b["gross_per"]
            dnp = None if (np1 is None or np2 is None) else np2 - np1
            dgp = None if (gp1 is None or gp2 is None) else gp2 - gp1
            g_out[g] = {
                "wo1": wo1, "wo2": wo2, "dwo": dwo,
                "np1": np1, "np2": np2, "dnp": dnp,
                "gp1": gp1, "gp2": gp2, "dgp": dgp,
                "n1": a["net"], "n2": b["net"], "c1": a["count"], "c2": b["count"],
                "tag": tag_for(dnp, dgp, dwo),
            }
        if g_out:
            out.setdefault(p["office"], {})[p["provider"]] = g_out
    return out


# ── Data transformation: pipeline format → reference JS format ────────────────

def _tcp(cp):
    """Map one pipeline checkpoint dict to the reference JS field names."""
    return {
        "thru":     cp["month_num"],
        "np2025":   cp["np25"],
        "wd2025":   cp["wd25"],
        "v2025":    cp["v25"],
        "dd2025":   cp["dd25"],
        "nps2025":  cp["npc25"],
        "rpd2025":  cp["rd25"],
        "rpv2025":  cp["spv25"],
        "vdd2025":  cp["vdd25"],
        "ddd2025":  cp["ddd25"],
        "np2026":   cp["np26"],
        "wd2026":   cp["wd26"],
        "v2026":    cp["v26"],
        "dd2026":   cp["dd26"],
        "nps2026":  cp["npc26"],
        "rpd2026":  cp["rd26"],
        "rpv2026":  cp["spv26"],
        "vdd2026":  cp["vdd26"],
        "ddd2026":  cp["ddd26"],
        "dRD":      cp["drd"],
        "pctRD":    cp["drd_pct"],
        "lvVisit":  cp["lev_spv"],
        "lvVDD":    cp["lev_vdd"],
        "lvDDD":    cp["lev_ddd"],
        "pctLvV":   cp["pct_spv"],
        "pctLvVDD": cp["pct_vdd"],
        "pctLvDDD": cp["pct_ddd"],
    }


def _transform_offices(office_data):
    """Return (D_list, OTHER_obj) in reference JS format."""
    D, OTHER = [], None
    for o in office_data:
        obj = {
            "office":         o["name"],
            "state":          o["state"] or "—",
            "isOther":        o["is_other"],
            "isFutureStart":  o.get("is_future_start", False),
            "sortDelta":      o["checkpoints"][-1]["drd"],
            "checkpoints":    [_tcp(cp) for cp in o["checkpoints"]],
        }
        if o["is_other"]:
            OTHER = obj
        else:
            D.append(obj)
    return D, OTHER


def _transform_providers(provider_data):
    """Return PD list in reference JS format."""
    PD = []
    for od in provider_data:
        providers = []
        other_obj = {"count": 0, "checkpoints": []}
        for p in od["providers"]:
            if p["is_other"]:
                other_obj = {
                    "count":       p.get("n_other", 0),
                    "checkpoints": [_tcp(cp) for cp in p["checkpoints"]],
                }
                continue
            providers.append({
                "provider":    p["name"],
                "ptype":       p["ptype"],
                "isNew":       p["is_new"],
                "sortDelta":   p["checkpoints"][-1]["drd"],
                "checkpoints": [_tcp(cp) for cp in p["checkpoints"]],
            })
        PD.append({
            "office":         od["office"],
            "state":          od["state"],
            "sortDelta":      providers[0]["checkpoints"][-1]["dRD"] if providers else None,
            "providers":      providers,
            "otherProviders": other_obj,
        })
    return PD


def _transform_data_summary(ds_data, provider_data):
    """Pass-through for the Data Summary payload, normalizing the state label and
    joining each provider's title/role (ptype) from the provider feed by (office,
    provider) — the role is not carried on the Data Summary structure itself."""
    role_map = {}
    for od in provider_data:
        for p in od["providers"]:
            if not p.get("is_other"):
                role_map[(od["office"], p["name"])] = p.get("ptype")
    out = []
    for o in ds_data:
        out.append({
            "office":    o["office"],
            "state":     o["state"] or "—",
            "metrics":   o["metrics"],
            "providers": [
                {"name": p["name"],
                 "role": role_map.get((o["office"], p["name"])),
                 "metrics": p["metrics"]}
                for p in o["providers"]
            ],
        })
    return out


def _t2_options(office_data):
    """Generate <option> elements for the Tab 2 office selector."""
    named = sorted(
        [o for o in office_data if not o["is_other"]],
        key=lambda o: o["name"],
    )
    lines = []
    for o in named:
        name = o["name"].replace("&", "&amp;").replace('"', "&quot;")
        label = f'{o["name"]} ({o["state"]})'.replace("&", "&amp;")
        lines.append(f'<option value="{name}">{label}</option>')
    return "\n".join(lines)


# ── HTML generation ───────────────────────────────────────────────────────────

def generate_html(office_data, provider_data, data_summary, mix_dataset=None, consolidated=None,
                  dollar_dataset=None):
    # dollar_dataset: verified procedure-dollar layer (mix_dollars). Wired into the payload
    # but DORMANT — no view consumes it yet (Phase 2 placement pending). Present so the
    # plumbing is proven end-to-end; rendering is added once placement is approved.
    D, OTHER = _transform_offices(office_data)
    PD       = _transform_providers(provider_data)
    DS       = _transform_data_summary(data_summary, provider_data)

    # Synthetic pinned company-total row (same JS shape as a D office; not in D so it is
    # excluded from sorting/filtering and the KPI sum, which already total 76 + Other).
    CONS = None
    if consolidated is not None:
        CONS = {
            "office":         consolidated["name"],
            "state":          consolidated["state"],
            "isOther":        False,
            "isConsolidated": True,
            "sortDelta":      consolidated["checkpoints"][-1]["drd"],
            "checkpoints":    [_tcp(cp) for cp in consolidated["checkpoints"]],
        }

    D_json     = json.dumps(D,     ensure_ascii=False, separators=(",", ":"))
    OTHER_json = json.dumps(OTHER, ensure_ascii=False, separators=(",", ":"))
    PD_json    = json.dumps(PD,    ensure_ascii=False, separators=(",", ":"))
    DS_json    = json.dumps(DS,    ensure_ascii=False, separators=(",", ":"))
    MIX_json   = json.dumps(mix_dataset or {}, ensure_ascii=False, separators=(",", ":"))
    CONS_json  = json.dumps(CONS, ensure_ascii=False, separators=(",", ":"))

    t2_opts = _t2_options(office_data)

    # Live rendered-provider count (single source of truth) — PD holds only named
    # providers (the "Other" rollup is carried separately), so this is exactly the
    # qualified rendered set the Mix Shift band counts. Never hardcode it.
    n_prov = sum(len(od["providers"]) for od in PD)

    # ── Month metadata: single source of truth, derived from the data ─────────
    months = pipeline.get_active_months()
    mtd = config.MTD_MONTH
    mtd_active = mtd in months and months[-1] == mtd   # partial month is the latest
    labels = [pipeline.MONTH_LABELS[m] + (" (MTD)" if (mtd_active and m == mtd) else "")
              for m in months]
    rng = (pipeline.MONTH_LABELS[months[0]] + "&ndash;" + pipeline.MONTH_LABELS[months[-1]]
           + " " + str(config.YEAR_1) + " vs " + str(config.YEAR_2))
    mtd_label = pipeline.MONTH_LABELS[mtd] if mtd_active else ""
    mtd_hint = (" <strong>" + labels[-1] + "</strong> = month-to-date (partial month); "
                "KPIs and YTD include it &mdash; not a full-month figure." if mtd_active else "")

    wd_y1 = round(sum(config.WORKING_DAYS.get((m, config.YEAR_1), 0) for m in months), 1)
    wd_y2 = round(sum(config.WORKING_DAYS.get((m, config.YEAR_2), 0) for m in months), 1)

    html = _TEMPLATE
    html = html.replace("__D_DATA__",     D_json)
    html = html.replace("__OTHER_DATA__", OTHER_json)
    html = html.replace("__PD_DATA__",    PD_json)
    html = html.replace("__DS_DATA__",    DS_json)
    html = html.replace("__MIX_DATA__",   MIX_json)
    html = html.replace("__CONSOLIDATED_DATA__", CONS_json)
    html = html.replace("__T2_OPTIONS__", t2_opts)
    html = html.replace("__NPROV__",      str(n_prov))
    html = html.replace("__WD25__",       str(wd_y1))
    html = html.replace("__WD26__",       str(wd_y2))
    html = html.replace("__MO_LABELS__",  json.dumps(labels, ensure_ascii=False))
    html = html.replace("__RANGE__",      rng)
    html = html.replace("__LASTMO__",     labels[-1])
    html = html.replace("__MTD_LABEL__",  json.dumps(mtd_label, ensure_ascii=False))
    html = html.replace("__MTD_ACTIVE__", "true" if mtd_active else "false")
    html = html.replace("__MTD_HINT__",   mtd_hint)
    html = html.replace("__MO_FIRST__",   pipeline.MONTH_LABELS[months[0]])
    html = html.replace("__MO_LAST__",    pipeline.MONTH_LABELS[months[-1]])
    html = html.replace("__REALIZATION_NAVTAB__", _realization_navtab(dollar_dataset))
    html = html.replace("__REALIZATION_TAB__", _realization_tab(dollar_dataset))
    html = html.replace("__MIX_DOLLARS_DATA__",
                        json.dumps(_mix_dollars_payload(dollar_dataset),
                                   ensure_ascii=False, separators=(",", ":")))
    return html


# ── Template (CSS + HTML + JS copied from reference, data injected) ───────────

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Revenue Driver Analysis — __RANGE__</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;font-size:13px;background:#f0f2f5;color:#222}
.page{max-width:1300px;margin:0 auto;padding:20px}
/* Header */
.header{background:#1F3864;color:#fff;padding:18px 24px;border-radius:8px;margin-bottom:14px}
.header h1{font-size:18px;font-weight:600;margin-bottom:4px}
.header p{font-size:11px;opacity:.7}
/* Top nav tabs */
.nav-tabs{display:flex;gap:0;margin-bottom:14px;background:#fff;border:0.5px solid #ddd;border-radius:8px;overflow:hidden}
.nav-tab{flex:1;padding:12px 0;text-align:center;font-size:13px;font-weight:500;cursor:pointer;color:#888;border:none;background:none;border-right:0.5px solid #ddd;transition:background .15s}
.nav-tab:last-child{border-right:none}
.nav-tab.on{background:#1F3864;color:#fff}
.nav-tab:hover:not(.on){background:#f5f7fa;color:#1F3864}
/* KPI row */
.scope-bar{background:#2E4D8A;color:#fff;font-size:11px;padding:5px 14px;border-radius:6px;margin-bottom:8px;font-weight:500;display:none}
.kpis{display:grid;gap:10px;margin-bottom:14px}
.kpis.k5{grid-template-columns:repeat(5,1fr)}
.kpis.k4{grid-template-columns:repeat(4,1fr)}
.kpi{background:#fff;border:0.5px solid #ddd;border-radius:8px;padding:12px 16px}
.kpi-lbl{font-size:11px;color:#888;margin-bottom:4px}
.kpi-val{font-size:20px;font-weight:600;color:#222}
.kpi-val.neg{color:#C0392B}.kpi-val.pos{color:#1a7a4a}
/* Month-to-date (partial month) flag on KPI ribbons */
.mtd-flag{background:#fff8e1;border:0.5px solid #f0d68a;color:#8a6d3b;font-size:11px;font-weight:500;padding:6px 12px;border-radius:6px;margin:-6px 0 14px}
.mtd-flag:empty{display:none}
/* Card */
.card{background:#fff;border:0.5px solid #ddd;border-radius:8px;padding:16px;margin-bottom:14px}
.ctrl-row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
.ctrl-row label{font-size:11px;color:#888;white-space:nowrap}
.ctrl-row select,.ctrl-row input{font-size:12px;padding:5px 8px;border-radius:6px;border:1px solid #ccc;background:#fff;color:#222;cursor:pointer}
.ctrl-row input{cursor:text;width:160px}
.ctrl-row select.big{font-size:13px;padding:7px 10px;font-weight:500;border-color:#378ADD;color:#1F3864;min-width:280px}
.hint{font-size:11px;color:#999;font-style:italic;margin-bottom:8px}
.section-lbl{font-size:11px;font-weight:600;color:#1F3864;text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px;padding-bottom:4px;border-bottom:1px solid #eee}
/* Tables */
table{width:100%;border-collapse:collapse}
table.hm{table-layout:fixed}
th{padding:6px 5px;font-size:10px;font-weight:600;color:#666;border-bottom:1.5px solid #ddd;text-align:center;white-space:nowrap;background:#fafafa}
th.l{text-align:left}
.dr{cursor:pointer}
.dr:hover td{filter:brightness(0.93)}
td{padding:5px 5px;text-align:center;font-size:11px;border-bottom:0.5px solid #f0f0f0;background:#fff}
td.l{text-align:left;font-weight:600;color:#222}
td.st{text-align:left;font-size:10px;color:#888;font-weight:400}
td.rk{text-align:center;font-size:10px;color:#aaa;width:28px}
/* Arrows */
.arrow{font-size:11px;color:#aaa;margin-left:4px;display:inline-block;transition:transform .15s}
.arrow.open{transform:rotate(90deg)}
/* Office drill (Tab 1) */
.drill-wrap td{padding:0!important}
.drill-inner{padding:12px 16px;border-left:4px solid #378ADD;background:#f0f4ff}
.drill-title{font-size:13px;font-weight:600;color:#1F3864;margin-bottom:8px}
.drill-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}
.cp-card{background:#fff;border:0.5px solid #ddd;border-radius:6px;padding:10px}
.cp-lbl{font-size:10px;font-weight:700;color:#1F3864;margin-bottom:6px;text-transform:uppercase;letter-spacing:.04em}
/* Provider drill (Tab 2) */
.prov-drill-wrap td{padding:0!important}
.prov-drill-inner{padding:10px 14px;border-left:4px solid #7B68EE;background:#f3f0ff}
.prov-drill-title{font-size:12px;font-weight:600;color:#5B4A9C;margin-bottom:6px}
/* Shared card styles */
.dl{display:flex;justify-content:space-between;font-size:10px;padding:2px 0;border-bottom:0.5px solid #f5f5f5}
.dl:last-child{border:none}
.dl .lb{color:#888}.dl .vl{font-weight:600}
.lev-sec{margin-top:6px;padding-top:6px;border-top:1px solid #eee}
.bar-lbl{font-size:9px;color:#888;margin:3px 0 2px}
.bar-track{height:9px;background:#eee;border-radius:4px;overflow:hidden;display:flex}
.bar-seg{height:100%}
.dom-lbl{font-size:10px;font-weight:700;margin-top:3px}
.leg-row{display:flex;gap:12px;margin-bottom:6px;flex-wrap:wrap}
.leg-item{display:flex;align-items:center;gap:3px;font-size:10px;color:#555}
.leg-sq{width:9px;height:9px;border-radius:2px}
.nc{color:#C0392B;font-weight:600}.pc{color:#1a7a4a;font-weight:600}
.nm{color:#999!important;font-style:italic;font-weight:400!important}
.other-sep{border-top:1.5px solid #ccc!important}
.other-row td{color:#999;font-style:italic}
/* Provider tab empty state */
.empty-state{text-align:center;padding:48px 24px;color:#aaa}
.empty-state .icon{font-size:36px;margin-bottom:12px}
.empty-state p{font-size:13px}
.footer{font-size:11px;color:#aaa;text-align:center;margin-top:10px}
/* Provider badges */
.badge{display:inline-block;font-size:9px;font-weight:600;padding:1px 5px;border-radius:3px;margin-left:5px;vertical-align:middle;white-space:nowrap}
.badge-gd{background:#dbeafe;color:#1e40af}
.badge-hyg{background:#d1fae5;color:#065f46}
.badge-spec{background:#ede9fe;color:#5b21b6}
.badge-new{background:#fef3c7;color:#92400e}
.badge-other{background:#f3f4f6;color:#6b7280}
.trend-up{color:#1a7a4a;font-size:12px;font-weight:700;margin-left:4px}
.trend-dn{color:#C0392B;font-size:12px;font-weight:700;margin-left:4px}
.trend-fl{color:#888;font-size:12px;font-weight:700;margin-left:4px}
.trend-legend{display:grid;grid-template-columns:1fr;gap:6px;background:#f8f9fa;border:0.5px solid #e0e0e0;border-radius:6px;padding:8px 12px;margin-bottom:8px;font-size:11px;color:#555}
.trend-legend-row{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
.trend-legend .tl-lbl{font-weight:600;color:#888;margin-right:2px;font-size:10px;text-transform:uppercase;letter-spacing:.04em;white-space:nowrap}
.trend-legend .tl-item{display:flex;align-items:center;gap:4px;white-space:nowrap}
.trend-legend .tl-div{width:1px;height:16px;background:#ddd;margin:0 4px}
.hm-swatch{display:inline-block;width:28px;height:12px;border-radius:2px;vertical-align:middle;margin-right:3px}
/* View 1 — Realization Diagnostic (own tab; per-office panes => CLASS-scoped, not #id,
   so the pre-rendered office panes don't create duplicate ids) */
.realz-slicer{display:flex;align-items:center;gap:10px;flex-wrap:wrap;border-left:4px solid #1F3864}
.realz-slicer label{font-size:12px;font-weight:600;color:#1F3864}
.realz-slicer select{padding:6px 10px;font-size:13px;border:0.5px solid #ccc;border-radius:6px;background:#fff;min-width:240px}
.realz-slicer-note{font-size:11px;color:#999;font-style:italic}
.realz-card{border-left:4px solid #C0392B}
.realz-card .rz-lead-stmt{background:#fdf6f5;border:0.5px solid #f0d7d3;border-radius:6px;padding:10px 14px;margin-bottom:12px;font-size:12.5px;line-height:1.5;color:#333}
.realz-card .rz-lead-stmt b{color:#1F3864}
.realz-card .rz-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px}
.realz-card .rz-ksub{font-size:10px;color:#aaa;margin-top:3px}
.realz-card .rz-ksub.pc{color:#1a7a4a}
.realz-card .rz-ksub.nc{color:#C0392B}
.realz-card table.rz-tbl{width:100%;border-collapse:collapse}
.realz-card .rz-tbl th{padding:6px 5px;font-size:10px;font-weight:600;color:#666;border-bottom:1.5px solid #ddd;text-align:center;white-space:nowrap;background:#fafafa}
.realz-card .rz-tbl th.l{text-align:left}
.realz-card .rz-tbl td{padding:7px 5px;text-align:center;font-size:12px;border-bottom:0.5px solid #f0f0f0;font-variant-numeric:tabular-nums}
.realz-card .rz-tbl td.l{text-align:left;font-weight:600;color:#222;font-variant-numeric:normal}
.realz-card .rz-tbl td.nc,.realz-card .rz-lead-stmt .nc{color:#C0392B}
.realz-card .rz-tbl td.pc{color:#1a7a4a}
.realz-card .nc{color:#C0392B}
.realz-card .pc{color:#1a7a4a}
.realz-card .rz-tag{display:inline-block;font-size:10px;font-weight:600;padding:2px 7px;border-radius:4px;white-space:nowrap;cursor:help}
.realz-card .rz-bad{background:#fbecea;color:#C0392B}
.realz-card .rz-warn{background:#fbeede;color:#b45309}
.realz-card .rz-good{background:#e6f4ec;color:#1a7a4a}
.realz-card .rz-mut{background:#f3f4f6;color:#6b7280}
.realz-card .rz-legend{font-size:10.5px;color:#666;margin-top:10px;display:grid;grid-template-columns:1fr 1fr;gap:5px 18px}
.realz-card .rz-legend b{color:#1F3864}
.realz-card .rz-def{font-style:italic;color:#555;font-size:11.5px;line-height:1.5;background:#fafbfc;border:0.5px solid #eee;border-radius:6px;padding:9px 13px;margin-bottom:12px}
.realz-card .rz-def b{color:#1F3864;font-style:normal}
.realz-card .rz-nav{font-size:11px;color:#8a8a8a;font-style:italic;margin:6px 0 2px}
.realz-card .rz-tbl th .rz-h2{font-size:9px;font-weight:400;color:#aaa;margin-top:2px;text-transform:none}
.realz-card .rz-tbl td.l .rz-sub{font-size:10px;font-weight:400;margin-top:2px}
.realz-card .rz-size{color:#999;font-weight:400}
.realz-card .rz-tbl th.rz-hero{background:#e9e6f6;color:#4a3f7a}
.realz-card .rz-tbl td.rz-hero{background:#f5f3fc}
.realz-card .rz-tbl th.rz-hero26,.realz-card .rz-tbl td.rz-hero26{background:#ece7fa}
.realz-card .rz-wo-amt{font-size:15px;font-weight:700;color:#3f2f73;line-height:1.1}
.realz-card .rz-wo-amt2{font-size:12px;font-weight:600;color:#6a5a93;line-height:1.1}
.realz-card .rz-wo-rate{font-size:10px;color:#888;margin-top:1px}
.realz-card .rz-credit{color:#1a7a4a!important}
.realz-card .rz-cr{color:#1a7a4a;font-weight:700;cursor:help}
.realz-card .rz-foot{font-size:10px;color:#888;margin-top:8px;font-style:italic}
/* click-to-explode: monthly Net/proc per row */
.realz-card tr.rz-row{cursor:pointer}
.realz-card tr.rz-row:hover{background:#fafaff}
.realz-card tr.rz-open{background:#f6f3fc}
.realz-card .rz-caret{display:inline-block;width:11px;margin-right:2px;color:#b3aacc;font-size:8px;transition:transform .12s}
.realz-card tr.rz-open .rz-caret{transform:rotate(90deg);color:#3f2f73}
.realz-card tr.rz-exp>td{background:#fbfafe;border-bottom:1px solid #e6e0f3;padding:10px 16px}
.realz-card .rz-exp-h{font-size:11px;font-weight:600;color:#3f2f73;margin-bottom:6px}
.realz-card .rz-exp-note{font-size:11.5px;color:#999;font-style:italic;padding:8px 0}
.realz-card .rzx-wrap{max-width:760px}
.realz-card svg.rzx{width:100%;height:auto;display:block}
.realz-card svg.rzx .grid{stroke:#eee;stroke-width:1}
.realz-card svg.rzx .ylab{fill:#aaa;font-size:9px;text-anchor:end}
.realz-card svg.rzx .xlab{fill:#888;font-size:10px;text-anchor:middle}
.realz-card svg.rzx .ln{fill:none;stroke-width:2.2}
.realz-card svg.rzx .lndash{stroke-width:2;stroke-dasharray:4 3;opacity:.5}
.realz-card svg.rzx .gap{fill:#C0392B;opacity:.07}
.realz-card svg.rzx .provband{fill:#f7f7f7;opacity:.7}
.realz-card svg.rzx .provlab{fill:#bbb;font-size:9px;text-anchor:middle}
.realz-card svg.rzx .endlab{font-size:10px;font-weight:600}
.realz-card table.rzx-tbl{width:100%;border-collapse:collapse;margin-top:8px;font-variant-numeric:tabular-nums}
.realz-card .rzx-tbl th,.realz-card .rzx-tbl td{padding:4px 6px;text-align:center;font-size:11px;border-bottom:0.5px solid #efeef5;white-space:nowrap}
.realz-card .rzx-tbl th{color:#888;font-weight:600;background:#fafafa}
.realz-card .rzx-tbl th.l,.realz-card .rzx-tbl td.l{text-align:left;color:#555;font-weight:600}
.realz-card .rzx-tbl td.nc{color:#C0392B}
.realz-card .rzx-tbl td.pc{color:#1a7a4a}
.realz-card .rzx-tbl .prov{background:#faf7fb;color:#a0468a}
/* Monthly trend card (class-scoped) */
.realz-monthly-card .rzm-callout{background:#fdf6f5;border:0.5px solid #f0d7d3;border-left:4px solid #C0392B;border-radius:6px;padding:10px 14px;margin:4px 0 12px;font-size:12.5px;line-height:1.5;color:#333}
.realz-monthly-card .rzm-callout b{color:#1F3864}
.realz-monthly-card .rzm-wrap{margin:6px 0 14px}
.realz-monthly-card .rzm-nodata{font-size:12px;color:#999;font-style:italic;padding:18px 0}
.realz-monthly-card svg.trend{width:100%;height:auto;display:block}
.realz-monthly-card svg.trend .grid{stroke:#eee;stroke-width:1}
.realz-monthly-card svg.trend .ylab{fill:#aaa;font-size:10px;text-anchor:end}
.realz-monthly-card svg.trend .xlab{fill:#888;font-size:11px;text-anchor:middle}
.realz-monthly-card svg.trend .ln{fill:none;stroke-width:2.4}
.realz-monthly-card svg.trend .lndash{stroke-width:2.2;stroke-dasharray:4 3;opacity:.55}
.realz-monthly-card svg.trend .gap{fill:#C0392B;opacity:.09}
.realz-monthly-card svg.trend .provband{fill:#f7f7f7;opacity:.7}
.realz-monthly-card svg.trend .provlab{fill:#bbb;font-size:9.5px;text-anchor:middle}
.realz-monthly-card svg.trend .endlab{font-size:11px;font-weight:600}
.realz-monthly-card .rzm-key{display:flex;gap:18px;font-size:11px;color:#666;margin-top:4px;padding-left:52px}
.realz-monthly-card .rzm-key i{display:inline-block;width:14px;height:3px;border-radius:2px;vertical-align:middle;margin-right:5px}
.realz-monthly-card .rzm-key i.gapkey{height:10px;background:#C0392B;opacity:.18}
.realz-monthly-card table.rzm-tbl{width:100%;border-collapse:collapse;margin-bottom:6px}
.realz-monthly-card .rzm-tbl th{padding:7px 8px;font-size:10px;font-weight:600;color:#666;border-bottom:1.5px solid #ddd;text-align:center;white-space:nowrap;background:#fafafa}
.realz-monthly-card .rzm-tbl th.l{text-align:left}
.realz-monthly-card .rzm-tbl td{padding:7px 8px;text-align:center;font-size:12px;border-bottom:0.5px solid #f0f0f0;font-variant-numeric:tabular-nums}
.realz-monthly-card .rzm-tbl td.l{text-align:left;font-weight:600;color:#222;font-variant-numeric:normal;white-space:nowrap}
.realz-monthly-card .rzm-tbl td.nc{color:#C0392B}
.realz-monthly-card .rzm-tbl td.pc{color:#1a7a4a}
.realz-monthly-card .rzm-h tr.ctxrow td{color:#999;background:#fbfbfb;font-size:11px}
.realz-monthly-card .rzm-h .prov{background:#faf7fb;color:#a0468a}
.realz-monthly-card .sk-head{font-size:11px;font-weight:600;color:#1F3864;margin:8px 0;padding-top:10px;border-top:0.5px solid #eee}
.realz-monthly-card .sk-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px 16px}
.realz-monthly-card .sk{border:0.5px solid #eee;border-radius:6px;padding:6px 8px}
.realz-monthly-card .sk-l{font-size:10.5px;font-weight:600;color:#444;margin-bottom:2px}
.realz-monthly-card svg.spark{width:100%;height:30px;display:block;overflow:visible}
/* Tab 4 — Data Summary (metric-major: office totals + per-metric explode) */
#tab4{
  --t4-line:#e2e8f0;--t4-ink:#1f2a44;--t4-soft:#5a6b85;--t4-faint:#94a3b8;--t4-zebra:#f5f8fc;
  --t4-up:#1a7a4a;--t4-up-bg:#e6f4ec;--t4-down:#C0392B;--t4-down-bg:#fbecea;--t4-accent:#2E4D8A;
  --t4-beat:#0e7490;--t4-beat-bg:#e0f2f9;--t4-trail:#b45309;--t4-trail-bg:#fbeede;
}
#tab4 .num{font-variant-numeric:tabular-nums;font-feature-settings:"tnum"}
#tab4 .t4up{color:var(--t4-up)} #tab4 .t4down{color:var(--t4-down)}
#tab4 .beat{color:var(--t4-beat)} #tab4 .trail{color:var(--t4-trail)}
#tab4 .t4-prompt{padding:40px 24px;text-align:center;color:#888}
#tab4 .t4-prompt .ic{font-size:32px;margin-bottom:10px}
/* office header + perspective strip — stays pinned while you scroll the metric grid */
#tab4 .t4anchor{position:sticky;top:0;z-index:20;box-shadow:0 6px 18px -10px rgba(20,40,74,.45)}
#tab4 .ohead{background:#1F3864;color:#fff;padding:10px 16px;border-radius:8px 8px 0 0;display:flex;justify-content:space-between;align-items:center;gap:12px}
#tab4 .ohead .who{font-weight:600;font-size:14px}
#tab4 .ohead .who small{font-weight:400;color:#c4d2e8;margin-left:8px;font-size:11px}
#tab4 .ohead .ohnote{font-size:10px;color:#aebfd8}
#tab4 .strip{display:grid;grid-template-columns:repeat(7,1fr);background:#fff;border:0.5px solid var(--t4-line);border-top:none;border-radius:0 0 8px 8px}
#tab4 .chip{padding:9px 11px;border-right:0.5px solid var(--t4-line)}
#tab4 .chip:last-child{border-right:none}
#tab4 .chip .m{font-size:10px;color:var(--t4-soft);text-transform:uppercase;letter-spacing:.4px;margin-bottom:3px}
#tab4 .chip .v{font-size:16px;font-weight:600;letter-spacing:-.2px}
#tab4 .chip .d{font-size:11px;font-weight:600;margin-top:2px}
#tab4 .chip .base{font-size:10px;color:var(--t4-faint);margin-top:1px}
#tab4 .pill{display:inline-block;padding:1px 6px;border-radius:5px;font-weight:600}
#tab4 .pill.t4up{background:var(--t4-up-bg)} #tab4 .pill.t4down{background:var(--t4-down-bg)}
/* controls */
#tab4 .controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:16px 2px 8px}
#tab4 .controls .lbl{font-size:11px;color:var(--t4-soft);font-weight:600;margin-right:2px}
#tab4 .seg{display:inline-flex;border:1px solid #cbd5e1;border-radius:7px;overflow:hidden}
#tab4 .seg button{font:inherit;font-size:11px;font-weight:600;border:none;background:#fff;color:var(--t4-soft);padding:6px 12px;cursor:pointer}
#tab4 .seg button.on{background:#1F3864;color:#fff}
#tab4 .linkbtn{background:none;border:none;color:var(--t4-accent);font:inherit;font-weight:600;cursor:pointer;padding:6px 4px;margin-left:auto}
#tab4 .linkbtn:hover{text-decoration:underline}
/* metric grid */
#tab4 .gridcard{background:#fff;border:0.5px solid #ddd;border-radius:8px;overflow:hidden}
#tab4 table.mg{width:100%;border-collapse:collapse;font-size:12px}
#tab4 table.mg th,#tab4 table.mg td{padding:7px 11px;text-align:right;border-bottom:0.5px solid var(--t4-line)}
#tab4 table.mg thead th{background:#1F3864;color:#fff;font-size:10px;text-transform:uppercase;letter-spacing:.4px;font-weight:600}
#tab4 table.mg thead th.lab{text-align:left}
#tab4 table.mg th.ytd,#tab4 table.mg td.ytd{background:rgba(46,77,138,.06)}
#tab4 table.mg thead th.ytd{background:#22406e}
/* metric (office-total) row = explode toggle */
#tab4 tr.mrow{cursor:pointer}
#tab4 tr.mrow.no-prov{cursor:default}
#tab4 tr.mrow>td{background:#eef3fa;border-bottom:0.5px solid #d7e2f0}
#tab4 tr.mrow:not(.no-prov):hover>td{background:#e4edf8}
#tab4 td.lab{text-align:left;font-weight:600;color:#1F3864}
#tab4 td.lab .tw{display:inline-block;width:16px;color:var(--t4-accent)}
#tab4 td.lab .cnt{font-weight:400;color:var(--t4-faint);font-size:10px;margin-left:6px}
#tab4 .cell .v{font-weight:600}
#tab4 .cell .d{font-size:10px;font-weight:600;margin-top:1px}
#tab4 .cell.full .g25,#tab4 .cell.full .g26{font-size:10px;color:var(--t4-faint)}
#tab4 .cell.full .gd{font-size:11px;font-weight:700;margin-top:1px}
#tab4 .cell .tag{font-size:9px;font-weight:700;color:var(--t4-faint);letter-spacing:.3px;margin-right:4px}
#tab4 .gapref{font-size:9px;color:var(--t4-faint);margin-top:1px}
/* provider rows */
#tab4 tr.prov td{background:#fff}
#tab4 tr.prov.alt td{background:var(--t4-zebra)}
#tab4 td.pname{text-align:left;padding-left:30px}
#tab4 td.pname .pn{font-weight:600}
#tab4 td.pname .role{display:block;font-size:10px;color:var(--t4-faint);font-weight:500}
#tab4 .flag{display:inline-block;font-size:9px;font-weight:700;letter-spacing:.3px;padding:1px 5px;border-radius:4px;margin-left:7px;vertical-align:1px;text-transform:uppercase}
#tab4 .flag.beat{background:var(--t4-beat-bg);color:var(--t4-beat)} #tab4 .flag.trail{background:var(--t4-trail-bg);color:var(--t4-trail)}
#tab4 .flag.inline{background:#eef2f6;color:var(--t4-faint)}
#tab4 tr.subhead td{background:#fafcfe;font-size:10px;color:var(--t4-faint);text-transform:uppercase;letter-spacing:.4px;padding:5px 12px;text-align:left}
#tab4 .legend{font-size:11px;color:var(--t4-faint);margin:12px 2px 0;display:flex;gap:18px;flex-wrap:wrap}
#tab4 .legend b{color:var(--t4-soft)}
#tab4 .hide{display:none}
#tab4 .linkbtn:focus-visible,#tab4 .seg button:focus-visible,#tab4 tr.mrow:focus-visible{outline:2px solid var(--t4-accent);outline-offset:-2px}
@media (max-width:880px){#tab4 .strip{grid-template-columns:repeat(2,1fr)}#tab4 .chip{border-bottom:0.5px solid var(--t4-line)}#tab4 .gridcard{overflow-x:auto}#tab4 .t4anchor{position:static}}
@media(max-width:880px){
  #tab4 .strip{grid-template-columns:repeat(2,1fr)}
  #tab4 .chip{border-bottom:0.5px solid var(--t4-line)}
  #tab4 .roster,#tab4 .anchor-card{overflow-x:auto}
}
/* Tab 2 provider table */
table.pt{table-layout:fixed;font-size:11px}
table.pt th{font-size:10px;background:#eef0ff;padding:5px}
td.pname{text-align:left;font-weight:600;color:#1F3864;font-size:11px}
@media(max-width:900px){
  .kpis.k5{grid-template-columns:repeat(2,1fr)}
  .kpis.k4{grid-template-columns:repeat(2,1fr)}
  .drill-grid{grid-template-columns:repeat(2,1fr)}
}
/* Tab 5 — Mix Shift (procedure composition per 100 visits; layout from mock, palette from dashboard) */
#tab5{--t5-navy:#1F3864;--t5-line:#e2e8f0;--t5-ink:#1f2a44;--t5-soft:#5a6b85;--t5-faint:#94a3b8;
  --t5-zebra:#f5f8fc;--t5-up:#1a7a4a;--t5-up-bg:#e6f4ec;--t5-down:#C0392B;--t5-down-bg:#fbecea;--t5-accent:#2E4D8A}
#tab5 .num{font-variant-numeric:tabular-nums;font-feature-settings:"tnum"}
#tab5 .t5intro{font-size:11px;color:var(--t5-faint);font-style:italic;margin:2px 2px 14px}
#tab5 .t5intro b{color:var(--t5-soft);font-style:normal}
#tab5 .t5band{background:var(--t5-navy);color:#fff;padding:10px 16px;border-radius:8px 8px 0 0;display:flex;justify-content:space-between;align-items:center;gap:12px}
#tab5 .t5band .who{font-weight:650;font-size:14px}
#tab5 .t5band .who small{font-weight:400;color:#c4d2e8;margin-left:8px;font-size:11px}
#tab5 .t5band .note{font-size:10px;color:#aebfd8;text-align:right}
#tab5 .t5note{background:#fff8e1;border:0.5px solid #f0d68a;border-top:none;color:#8a6d3b;font-size:11px;font-weight:500;padding:7px 13px}
#tab5 .t5note .t5inactive{font-style:italic;color:var(--t5-down);font-weight:700}
#tab5 table.t5tbl{width:100%;border-collapse:collapse;font-size:12px;background:#fff;border:0.5px solid var(--t5-line);border-top:none;border-radius:0 0 8px 8px;overflow:hidden}
#tab5 table.t5tbl th,#tab5 table.t5tbl td{padding:8px 13px;text-align:right;border-bottom:0.5px solid var(--t5-line)}
#tab5 table.t5tbl thead th{background:var(--t5-navy);color:#fff;font-size:10px;text-transform:uppercase;letter-spacing:.4px;font-weight:600}
#tab5 table.t5tbl thead th.lab{text-align:left}
#tab5 table.t5tbl td.proc{text-align:left;font-weight:650;color:var(--t5-navy)}
#tab5 table.t5tbl th.dc,#tab5 table.t5tbl td.dc{background:rgba(46,77,138,.06)}
#tab5 table.t5tbl thead th.dc{background:#22406e}
#tab5 tr.t5prov{cursor:pointer}
#tab5 tr.t5prov:hover td{background:var(--t5-zebra)}
#tab5 td.proc .tw{display:inline-block;width:15px;color:var(--t5-accent)}
#tab5 .t5delta{font-weight:700}
#tab5 .t5up{color:var(--t5-up)}#tab5 .t5down{color:var(--t5-down)}
#tab5 .t5vs{font-size:11px;color:var(--t5-faint)}
#tab5 .t5muted{color:var(--t5-faint)}
#tab5 .t5chip{display:inline-block;font-size:9px;font-weight:700;letter-spacing:.3px;padding:1px 6px;border-radius:4px;margin-left:6px;text-transform:uppercase}
#tab5 .t5chip.hi{background:var(--t5-up-bg);color:var(--t5-up)}
#tab5 .t5chip.lo{background:var(--t5-down-bg);color:var(--t5-down)}
#tab5 .t5chip.in{background:#eef2f6;color:var(--t5-faint)}
#tab5 tr.t5detail td{padding:0;background:#fbfcfe}
#tab5 .t5dwrap{padding:8px 14px 16px}
#tab5 .t5dh{font-size:10px;text-transform:uppercase;letter-spacing:.4px;color:var(--t5-soft);padding:8px 2px 6px;font-weight:600}
#tab5 table.t5mo{width:100%;border-collapse:collapse;font-size:11px}
#tab5 table.t5mo th,#tab5 table.t5mo td{padding:6px 10px;text-align:right;border-bottom:0.5px solid var(--t5-line)}
#tab5 table.t5mo th{background:#f0f4f9;font-size:10px;text-transform:uppercase;letter-spacing:.3px;color:var(--t5-soft);font-weight:600}
#tab5 table.t5mo th.l,#tab5 table.t5mo td.l{text-align:left}
#tab5 table.t5mo td.l{font-weight:600;color:var(--t5-ink)}
#tab5 tr.t5y26 td{background:#eef3fa}
#tab5 tr.t5bm td{color:var(--t5-soft)}
#tab5 tr.t5bm td.l{color:var(--t5-faint);font-style:italic;font-weight:500}
#tab5 tr.t5sep td{border-top:2px solid #d7e2f0}
#tab5 .t5prompt{padding:40px 24px;text-align:center;color:#888}
#tab5 .t5prompt .ic{font-size:32px;margin-bottom:10px}
#tab5 .t5legend{font-size:11px;color:var(--t5-faint);margin:14px 2px 0;display:flex;gap:20px;flex-wrap:wrap}
#tab5 .t5legend b{color:var(--t5-soft)}
#tab5 tr.t5prov:focus-visible{outline:2px solid var(--t5-accent);outline-offset:-2px}
/* Preventive / Other — residual, hygienist-driven category set apart from the 9 procedures */
#tab5 tr.t5sec td{background:#eef2f7;color:var(--t5-soft);font-size:10px;text-transform:uppercase;letter-spacing:.5px;font-weight:700;text-align:left;border-top:2px solid var(--t5-accent)}
#tab5 tr.t5other td{background:#f6f4fb}
#tab5 tr.t5other:hover td{background:#efeaf8}
#tab5 tr.t5other td.proc{color:#5b4a86;font-style:italic;font-weight:600}
#tab5 .t5oinfo{cursor:help;color:var(--t5-faint);font-weight:400;margin-left:5px}
#tab5 table.t5tbl td.num{white-space:nowrap}
/* Volume reality — visits anchor (frames the view), volume-leads columns, mix subordinate */
#tab5 .t5anchor{display:flex;flex-direction:column;gap:6px;background:#fbfcfe;border:0.5px solid var(--t5-line);border-radius:8px;padding:11px 16px;margin-bottom:10px}
#tab5 .t5aleg{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
#tab5 .t5aleg .t5alab{min-width:160px;font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--t5-soft);font-weight:700;line-height:1.25}
#tab5 .t5aleg .t5anum{font-size:17px;font-weight:750;color:var(--t5-ink);font-variant-numeric:tabular-nums}
#tab5 .t5anchor .t5aarr{color:var(--t5-faint);font-weight:400;margin:0 5px}
#tab5 .t5anchor .t5achg{font-size:13px;font-weight:750;padding:1px 8px;border-radius:5px}
#tab5 .t5achg.t5adown{color:var(--t5-down);background:var(--t5-down-bg)}
#tab5 .t5achg.t5aup{color:var(--t5-up);background:var(--t5-up-bg)}
#tab5 .t5achg.t5ana{color:var(--t5-faint);background:#eef2f6}
#tab5 .t5anchor .t5achg small{font-weight:600;font-size:9px;opacity:.85}
#tab5 table.t5tbl thead th.grpv{background:#1a3a63;text-align:center}
#tab5 table.t5tbl thead th.grpm{background:#41506b;color:#c9d5ea;text-align:center}
#tab5 table.t5tbl th.mx,#tab5 table.t5tbl td.mx{background:rgba(46,77,138,.05)}
#tab5 table.t5tbl td.mx{color:var(--t5-soft);font-size:11px}
#tab5 table.t5tbl th.vsep,#tab5 table.t5tbl td.vsep{border-left:2px solid #cdd9ea}
#tab5 .t5cd{font-weight:750}
#tab5 .t5cd small{font-weight:600;font-size:9px;opacity:.85}
#tab5 .t5cap{font-size:11px;color:var(--t5-faint);font-style:italic;margin:9px 2px 0}
#tab5 table.t5mo tr.t5cntrow td{background:#f3f7fc;font-variant-numeric:tabular-nums}
#tab5 table.t5mo tr.t5cntrow td.l{font-style:normal;color:var(--t5-ink);font-weight:600}
#tab5 table.t5tbl thead th.mx{background:#e6ecf5;color:#2f3e5c}
#tab5 .t5anchor .t5awin{display:block;font-size:9px;color:var(--t5-faint);font-weight:600;letter-spacing:.3px;text-transform:none}
#tab5 .t5anchor .t5asub{font-size:10px;color:var(--t5-faint);font-style:italic;border-top:0.5px dashed var(--t5-line);padding-top:5px;margin-top:1px}
#tab5 .t5momtd{font-weight:700;font-size:8px;color:var(--t5-faint)}
/* View 2 — dollar detail block in the procedure expand (realization-led) */
#tab5 .t5dol{padding-bottom:6px}
#tab5 .t5dolh{display:flex;align-items:center;gap:10px}
#tab5 .t5dtag{font-size:9px;font-weight:700;letter-spacing:.3px;padding:1px 7px;border-radius:4px;text-transform:none}
#tab5 .t5dtag.t5dbad{background:var(--t5-down-bg);color:var(--t5-down)}
#tab5 .t5dtag.t5dwarn{background:#fbeede;color:#b45309}
#tab5 .t5dtag.t5dgood{background:var(--t5-up-bg);color:var(--t5-up)}
#tab5 .t5dtag.t5dmut{background:#eef2f6;color:var(--t5-faint)}
#tab5 table.t5doltbl{max-width:560px}
#tab5 table.t5doltbl tr.t5dollead td{background:#eef3fb;font-weight:600}
#tab5 table.t5doltbl tr.t5dollead td.l{color:var(--t5-navy)}
#tab5 table.t5doltbl tr.t5dolctrl td{color:var(--t5-faint);background:#fbfbfc}
#tab5 table.t5doltbl .t5dctl{font-size:8px;text-transform:uppercase;letter-spacing:.3px;color:var(--t5-faint);border:0.5px solid var(--t5-line);border-radius:3px;padding:0 3px;margin-left:4px}
#tab5 .t5intro>div{margin-bottom:3px}
#tab5 .t5intro>div:last-child{margin-bottom:0}
@media(max-width:880px){#tab5 .t5band{flex-direction:column;align-items:flex-start;gap:4px}#tab5 .t5band .note{text-align:left}#tab5 table.t5tbl,#tab5 .t5dwrap{display:block;overflow-x:auto}}
</style>
</head>
<body>
<div class="page">

<div class="header">
  <h1>Revenue Driver Analysis &mdash; __RANGE__</h1>
  <p>Rev/Day = $/Visit &times; Visits/Dr Day &times; Dr Days/Day &nbsp;&bull;&nbsp; 76 offices &nbsp;&bull;&nbsp; __NPROV__ named providers &nbsp;&bull;&nbsp; Providers filtered to material contributors only: cumulative 90% of office production + 2% individual floor (ranked by peak year production &mdash; captures new providers) &nbsp;&bull;&nbsp; Noise providers (temp, insurance, unassigned, etc.) excluded</p>
</div>

<!-- TOP NAV TABS -->
<div class="nav-tabs">
  <button class="nav-tab on" id="navTab1" onclick="switchTab(1)">&#127970; Office Analysis</button>
  <button class="nav-tab" id="navTab2" onclick="switchTab(2)">&#128101; Provider Deep Dive</button>
  <button class="nav-tab" id="navTab3" onclick="switchTab(3)">&#128202; Doctor Rank View</button>
  <button class="nav-tab" id="navTab4" onclick="switchTab(4)">&#128203; Data Summary</button>
  <button class="nav-tab" id="navTab5" onclick="switchTab(5)">&#128138; Mix Shift</button>__REALIZATION_NAVTAB__
</div>

<!-- ═══════════════════════════════════════════════════
     TAB 1 — OFFICE VIEW
════════════════════════════════════════════════════ -->
<div id="tab1">
  <div class="scope-bar" id="t1ScopeBar"></div>
  <div class="kpis k5">
    <div class="kpi"><div class="kpi-lbl" id="t1Lbl25">Rev/Day &mdash; 2025</div><div class="kpi-val" id="t1Kpi25">&mdash;</div></div>
    <div class="kpi"><div class="kpi-lbl" id="t1Lbl26">Rev/Day &mdash; 2026</div><div class="kpi-val" id="t1Kpi26">&mdash;</div></div>
    <div class="kpi"><div class="kpi-lbl">&Delta; Rev/Day</div><div class="kpi-val" id="t1KpiDelta">&mdash;</div></div>
    <div class="kpi"><div class="kpi-lbl">YTD production gap</div><div class="kpi-val" id="t1KpiGap">&mdash;</div></div>
    <div class="kpi"><div class="kpi-lbl">New patients lost YTD</div><div class="kpi-val" id="t1KpiNP">&mdash;</div></div>
  </div>
  <div class="mtd-flag" id="t1Mtd"></div>
  <div class="card">
    <div class="ctrl-row">
      <label>Show:</label>
      <select id="t1Show">
        <option value="all">All 76 offices</option>
        <option value="25">Top 25 declining</option>
        <option value="15">Top 15 declining</option>
        <option value="best">Top 15 improving</option>
      </select>
      <label>Metric:</label>
      <select id="t1Metric">
        <option value="delta">&#916; Rev/Day ($)</option>
        <option value="pct">% change</option>
      </select>
      <label>Direction:</label>
      <select id="t1Dir">
        <option value="all" selected>All</option>
        <option value="decl">Declining &mdash; &Delta; Rev/Day &lt; 0</option>
        <option value="grow">Growing &mdash; &Delta; Rev/Day &gt; 0</option>
      </select>
      <label>State:</label>
      <select id="t1State">
        <option value="">All states</option>
        <option>Alabama</option>
        <option>Arkansas</option>
        <option>Florida</option>
        <option>Kentucky</option>
        <option>Tennessee</option>
      </select>
      <label>Search:</label>
      <input type="text" id="t1Search" placeholder="office name...">
    </div>
    <div class="trend-legend">
      <div class="trend-legend-row">
        <span class="tl-lbl">Heat map:</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#7f0000"></span>&minus;$4,000+</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#C0392B"></span>&minus;$2,500 to &minus;$4,000</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#e88080"></span>&minus;$1,000 to &minus;$2,500</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#fdecea"></span>&minus;$300 to &minus;$1,000</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#f5b8b8;border:0.5px solid #e88080"></span>0 to &minus;$300</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#a8dbb8;border:0.5px solid #82c4a0"></span>0 to +$500</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#82c4a0"></span>+$500 to +$2,000</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#0f5032"></span>+$2,000+</span>
      </div>
      <div class="trend-legend-row">
        <span class="tl-lbl">YTD __LASTMO__ trend:</span>
        <span class="tl-item"><span class="trend-up">&#8593;</span> Improving &mdash; gap narrowing vs first available month</span>
        <span class="tl-item"><span class="trend-dn">&#8595;</span> Worsening &mdash; gap widening vs first available month</span>
        <span class="tl-item"><span class="trend-fl">&#8594;</span> Stable &mdash; within &plusmn;5% of first available month</span>
        <span class="tl-item" style="color:#aaa;font-size:10px;font-style:italic">Hover arrow for baseline month &nbsp;&bull;&nbsp; &Delta; Rev/Day mode only</span>
      </div>
    </div>
    <div class="hint">Click any office row to expand the lever breakdown across all YTD checkpoints</div>
    <div id="t1Wrap"></div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════
     TAB 2 — PROVIDER VIEW
════════════════════════════════════════════════════ -->
<div id="tab2" style="display:none">
  <div class="kpis k4" id="t2KpiRow">
    <div class="kpi"><div class="kpi-lbl" id="t2LblOff">Select an office above</div><div class="kpi-val" id="t2KpiProvs">&mdash;</div></div>
    <div class="kpi"><div class="kpi-lbl">Rev/Day 2025</div><div class="kpi-val" id="t2Kpi25">&mdash;</div></div>
    <div class="kpi"><div class="kpi-lbl">Rev/Day 2026</div><div class="kpi-val" id="t2Kpi26">&mdash;</div></div>
    <div class="kpi"><div class="kpi-lbl">&Delta; Rev/Day</div><div class="kpi-val" id="t2KpiDelta">&mdash;</div></div>
  </div>
  <div class="mtd-flag" id="t2Mtd"></div>
  <div class="card">
    <div class="ctrl-row">
      <label>Office:</label>
      <select id="t2OfficeSel" class="big">
        <option value="">-- Select an office --</option>
        __T2_OPTIONS__
      </select>
      <label>Sort providers by:</label>
      <select id="t2Sort">
        <option value="delta">Worst YoY decline</option>
        <option value="np25">Highest 2025 production</option>
        <option value="np26">Highest 2026 production</option>
        <option value="best">Best YoY growth</option>
      </select>
      <label>Metric:</label>
      <select id="t2Metric">
        <option value="delta">&#916; Rev/Day ($)</option>
        <option value="pct">% change</option>
      </select>
      <label>Direction:</label>
      <select id="t2Dir">
        <option value="all" selected>All</option>
        <option value="decl">Declining &mdash; &Delta; Rev/Day &lt; 0</option>
        <option value="grow">Growing &mdash; &Delta; Rev/Day &gt; 0</option>
      </select>
    </div>
    <div class="trend-legend">
      <div class="trend-legend-row">
        <span class="tl-lbl">Heat map:</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#7f0000"></span>&minus;$4,000+</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#C0392B"></span>&minus;$2,500 to &minus;$4,000</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#e88080"></span>&minus;$1,000 to &minus;$2,500</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#fdecea"></span>&minus;$300 to &minus;$1,000</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#f5b8b8;border:0.5px solid #e88080"></span>0 to &minus;$300</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#a8dbb8;border:0.5px solid #82c4a0"></span>0 to +$500</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#82c4a0"></span>+$500 to +$2,000</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#0f5032"></span>+$2,000+</span>
      </div>
      <div class="trend-legend-row">
        <span class="tl-lbl">YTD __LASTMO__ trend:</span>
        <span class="tl-item"><span class="trend-up">&#8593;</span> Improving &mdash; gap narrowing vs first available month</span>
        <span class="tl-item"><span class="trend-dn">&#8595;</span> Worsening &mdash; gap widening vs first available month</span>
        <span class="tl-item"><span class="trend-fl">&#8594;</span> Stable &mdash; within &plusmn;5% of first available month</span>
        <span class="tl-item" style="color:#aaa;font-size:10px;font-style:italic">Hover arrow for baseline month &nbsp;&bull;&nbsp; &Delta; Rev/Day mode only</span>
      </div>
    </div>
    <div class="hint">Select an office to see its providers &rarr; click a provider row to expand the lever breakdown</div>
    <div id="t2Wrap">
      <div class="empty-state">
        <div class="icon">&#128101;</div>
        <p>Select an office from the dropdown above to see provider performance</p>
      </div>
    </div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════
     TAB 3 — DOCTOR RANK VIEW (cross-office)
════════════════════════════════════════════════════ -->
<div id="tab3" style="display:none">
  <div class="scope-bar" id="t3ScopeBar"></div>
  <div class="kpis k4">
    <div class="kpi"><div class="kpi-lbl" id="t3KpiProvsLbl">Doctors shown</div><div class="kpi-val" id="t3KpiProvs">&mdash;</div></div>
    <div class="kpi"><div class="kpi-lbl" id="t3Lbl25">DSO Rev/Day &mdash; 2025</div><div class="kpi-val" id="t3Kpi25">&mdash;</div></div>
    <div class="kpi"><div class="kpi-lbl" id="t3Lbl26">DSO Rev/Day &mdash; 2026</div><div class="kpi-val" id="t3Kpi26">&mdash;</div></div>
    <div class="kpi"><div class="kpi-lbl">&Delta; Rev/Day</div><div class="kpi-val" id="t3KpiDelta">&mdash;</div></div>
  </div>
  <div class="mtd-flag" id="t3Mtd"></div>
  <div class="card">
    <div class="ctrl-row">
      <label>Show:</label>
      <select id="t3Show">
        <option value="25">Top 25</option>
        <option value="50">Top 50</option>
        <option value="100">Top 100</option>
        <option value="150">Top 150</option>
        <option value="all" id="t3ShowAll" selected>All doctors</option>
      </select>
      <label>Metric:</label>
      <select id="t3Metric">
        <option value="delta">&#916; Rev/Day ($)</option>
        <option value="pct">% change</option>
      </select>
      <label>Direction:</label>
      <select id="t3Dir">
        <option value="all" selected>All</option>
        <option value="decl">Declining &mdash; &Delta; Rev/Day &lt; 0</option>
        <option value="grow">Growing &mdash; &Delta; Rev/Day &gt; 0</option>
      </select>
      <label>State:</label>
      <select id="t3State">
        <option value="">All states</option>
        <option>Alabama</option>
        <option>Arkansas</option>
        <option>Florida</option>
        <option>Kentucky</option>
        <option>Tennessee</option>
      </select>
      <label>Search:</label>
      <input type="text" id="t3Search" placeholder="provider or office...">
    </div>
    <div class="trend-legend">
      <div class="trend-legend-row">
        <span class="tl-lbl">Heat map:</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#7f0000"></span>&minus;$4,000+</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#C0392B"></span>&minus;$2,500 to &minus;$4,000</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#e88080"></span>&minus;$1,000 to &minus;$2,500</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#fdecea"></span>&minus;$300 to &minus;$1,000</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#f5b8b8;border:0.5px solid #e88080"></span>0 to &minus;$300</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#a8dbb8;border:0.5px solid #82c4a0"></span>0 to +$500</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#82c4a0"></span>+$500 to +$2,000</span>
        <span class="tl-item"><span class="hm-swatch" style="background:#0f5032"></span>+$2,000+</span>
      </div>
      <div class="trend-legend-row">
        <span class="tl-lbl">Provider type:</span>
        <span class="tl-item"><span class="badge badge-gd">General Dentist</span></span>
        <span class="tl-item"><span class="badge badge-hyg">Hygienist</span></span>
        <span class="tl-item"><span class="badge badge-spec">Specialist</span></span>
        <span class="tl-item"><span class="badge badge-new">NEW</span></span>
        <span class="tl-div"></span>
        <span class="tl-lbl">YTD __LASTMO__ trend:</span>
        <span class="tl-item"><span class="trend-up">&#8593;</span> Improving</span>
        <span class="tl-item"><span class="trend-dn">&#8595;</span> Worsening</span>
        <span class="tl-item"><span class="trend-fl">&#8594;</span> Stable</span>
      </div>
    </div>
    <div class="hint">All named providers across 76 offices &mdash; sorted by worst YoY decline &bull; click any provider row to expand the lever breakdown across all YTD checkpoints</div>
    <div id="t3Wrap"></div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════
     TAB 4 — DATA SUMMARY (show your work)
════════════════════════════════════════════════════ -->
<div id="tab4" style="display:none">
  <div class="card">
    <div class="ctrl-row">
      <label>State:</label>
      <select id="t4State">
        <option value="">All states</option>
        <option>Alabama</option>
        <option>Arkansas</option>
        <option>Florida</option>
        <option>Kentucky</option>
        <option>Tennessee</option>
      </select>
      <label>Office:</label>
      <select id="t4Office" class="big"></select>
    </div>
    <div class="hint">Transparent view of the underlying source data driving every calculation &mdash; monthly values are individual-month actuals; YTD Total sums the months (ratio metrics recomputed from YTD totals). Currency rounded to whole dollars.__MTD_HINT__</div>
    <div id="t4Wrap"></div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════
     TAB 5 — MIX SHIFT
════════════════════════════════════════════════════ -->
<div id="tab5" style="display:none">
  <div class="card">
    <div class="ctrl-row">
      <label>State:</label>
      <select id="t5State">
        <option value="">All states</option>
        <option>Alabama</option>
        <option>Arkansas</option>
        <option>Florida</option>
        <option>Kentucky</option>
        <option>Tennessee</option>
      </select>
      <label>Office:</label>
      <select id="t5Office"></select>
      <label>Provider:</label>
      <select id="t5Provider" class="big"></select>
    </div>
    <div class="t5intro"><div>Procedure composition shown as <b>per 100 visits</b> (mix, not raw volume). <b>&Delta; = 2026 &minus; 2025</b> (YoY shift).</div><div>__MTD_HINT__</div><div>A procedure shows if it had activity in <b>either</b> year. Click a procedure for its monthly shape.</div><div><b>Preventive / Other</b> captures activity outside the 9 tracked procedures &mdash; mostly hygiene/preventive (specialty at surgical &amp; ortho offices), sectioned separately.</div></div>
    <div id="t5Wrap"></div>
    <div class="t5legend">
      <span><b>&Delta;</b> YoY shift in per-100-visits &middot; <span class="t5up">&#9650; up</span> &middot; <span class="t5down">&#9660; down</span></span>
      <span><b>vs Company</b> rate vs the company average &middot; <span class="t5up">above</span> / <span class="t5down">below</span> / in line</span>
      <span><b>Click a procedure</b> to expand its monthly shape (__MO_FIRST__&ndash;__MO_LAST__, 2025/2026 with state &amp; company)</span>
    </div>
  </div>
</div>

__REALIZATION_TAB__
<div class="footer">Generated from source data &mdash; __RANGE__ &mdash; 76 offices &mdash; Provider threshold: 90% production + 2% floor &mdash; Noise providers excluded</div>
</div>

<script>
var MO=__MO_LABELS__;            // active-month labels (partial month carries " MTD")
var MTD_LABEL=__MTD_LABEL__;     // e.g. "Jun" when a partial month is active, else ""
var MTD_ON=__MTD_ACTIVE__;       // true when the latest active month is month-to-date
var WD25=__WD25__,WD26=__WD26__;
function lastCp(c){return c[c.length-1];}                         // latest YTD checkpoint
function moHeaders(){return MO.map(function(m){return '<th>YTD '+m+'</th>';}).join('');}
function mtdBanner(){return MTD_ON?'<div>&#9888; '+MTD_LABEL+' (MTD) is a partial month &mdash; KPI cards, YTD totals, and ordering include a month-to-date figure, not a full month.</div>':'';}

var D=__D_DATA__;
var OTHER=__OTHER_DATA__;
var CONSOLIDATED=__CONSOLIDATED_DATA__;   // company-total pinned row (76 + Other); null if not built
var PD=__PD_DATA__;
var PD_MAP={};
for(var i=0;i<PD.length;i++){PD_MAP[PD[i].office]=PD[i];}

var DS=__DS_DATA__;
var DS_MAP={};
for(var i=0;i<DS.length;i++){DS_MAP[DS[i].office]=DS[i];}

// Flatten PD into a single cross-office list of named providers (Tab 3)
var PR_ALL=[];
for(var i=0;i<PD.length;i++){
  var od=PD[i];
  for(var j=0;j<od.providers.length;j++){
    var p=od.providers[j];
    PR_ALL.push({
      provider:    p.provider,
      office:      od.office,
      state:       od.state||'&mdash;',
      ptype:       p.ptype,
      isNew:       p.isNew,
      sortDelta:   p.sortDelta,
      checkpoints: p.checkpoints
    });
  }
}

var t1OpenKey=null;
var t2OpenProv=null;
var t3OpenKey=null;
var currentTab=1;

// ── Helpers ───────────────────────────────────────────────────────────────────
function trendArrow(checkpoints){
  if(!checkpoints||checkpoints.length<2)return '';
  var last=checkpoints.length-1;
  var v_last=checkpoints[last].dRD;
  if(v_last==null)return '';
  var v_base=null,base_mo='';
  for(var i=0;i<last;i++){
    if(checkpoints[i].dRD!=null){v_base=checkpoints[i].dRD;base_mo=MO[i];break;}
  }
  if(v_base==null)return '';
  var diff=v_last-v_base;
  var pct=v_base!==0?Math.abs(diff/v_base)*100:0;
  var tip='vs YTD '+base_mo+(base_mo!==MO[0]?' (first available)':'');
  if(pct<5)return '<span class="trend-fl" title="Stable within 5% — '+tip+'">&#8594;</span>';
  if(diff>0)return '<span class="trend-up" title="Improving — '+tip+'">&#8593;</span>';
  return '<span class="trend-dn" title="Worsening — '+tip+'">&#8595;</span>';
}

// Direction filter — uses the latest YTD checkpoint Δ Rev/Day. Rows with a
// null/zero Δ are excluded from both Declining and Growing.
function dirPass(checkpoints,dir){
  if(dir==='all'||!dir)return true;
  var d=(checkpoints&&checkpoints.length)?lastCp(checkpoints).dRD:null;
  if(d==null)return false;
  return dir==='decl'?d<0:d>0;
}

function hcol(v,metric){
  if(v==null)return 'background:#fafafa;color:#bbb';
  if(v==='N/M')return 'background:#f4f4f4;color:#999;font-style:italic';
  if(metric==='delta'){
    if(v<=-4000)return 'background:#7f0000;color:#fff';
    if(v<=-2500)return 'background:#C0392B;color:#fff';
    if(v<=-1000)return 'background:#e88080;color:#7f0000';
    if(v<= -300)return 'background:#fdecea;color:#9C0006';
    if(v<    0) return 'background:#fff5f5;color:#9C0006';
    if(v>= 2000)return 'background:#0f5032;color:#fff';
    if(v>=  500)return 'background:#82c4a0;color:#0f5032';
    if(v>    0) return 'background:#e9f7ef;color:#1a5e36';
  } else {
    if(v<=-50)return 'background:#7f0000;color:#fff';
    if(v<=-25)return 'background:#C0392B;color:#fff';
    if(v<=-10)return 'background:#e88080;color:#7f0000';
    if(v<= -3)return 'background:#fdecea;color:#9C0006';
    if(v<   0)return 'background:#fff5f5;color:#9C0006';
    if(v>=  20)return 'background:#0f5032;color:#fff';
    if(v>=   5)return 'background:#82c4a0;color:#0f5032';
    if(v>   0) return 'background:#e9f7ef;color:#1a5e36';
  }
  return 'background:#fafafa;color:#888';
}
function fd(v){if(v==null)return '&mdash;';return(v<0?'&minus;$':'$')+Math.abs(Math.round(v)).toLocaleString();}
function fp(v){if(v==null)return '&mdash;';if(v==='N/M')return '<span class="nm" title="Not Meaningful — 2025 baseline is negative, zero, or near-zero">N/M</span>';return(v<0?'':'+')+''+v.toFixed(1)+'%';}
function fn(v){if(v==null)return '&mdash;';return Math.round(v).toLocaleString();}
function fm(v,metric){return metric==='pct'?fp(v):fd(v);}
function fv(v){if(v==null)return '&mdash;';return v.toFixed(2);}
function fmv(v){if(v==null)return '&mdash;';return(v<0?'&minus;$':'$')+Math.abs(v/1e6).toFixed(1)+'M';}
function fk(v){if(v==null)return '&mdash;';return(v<0?'&minus;$':'$')+Math.abs(Math.round(v)).toLocaleString();}
function sk(id,val,neg){var el=document.getElementById(id);if(!el)return;el.innerHTML=val;el.className='kpi-val'+(neg?' neg':'');}

function domPct(a,b,c){
  var t=Math.abs(a||0)+Math.abs(b||0)+Math.abs(c||0);
  if(!t)return [0,0,0];
  return [Math.abs(a||0)/t*100,Math.abs(b||0)/t*100,Math.abs(c||0)/t*100];
}

// ── Shared: lever card builder ────────────────────────────────────────────────
function buildCpCard(cp,i,accentColor){
  var hasL=cp.lvVisit!=null;
  var pV=0,pVDD=0,pDDD=0,domLev='&mdash;',domCol='#888';
  if(hasL){
    var dp=domPct(cp.lvVisit,cp.lvVDD,cp.lvDDD);
    pV=dp[0];pVDD=dp[1];pDDD=dp[2];
    if(pV>=pVDD&&pV>=pDDD){domLev='$/Visit';domCol='#C0392B';}
    else if(pVDD>=pDDD){domLev='Visits/Dr Day';domCol='#7B68EE';}
    else{domLev='Dr Days/Day';domCol='#D2691E';}
  }
  var dCl=(cp.dRD||0)<0?'nc':'pc';
  var rpvD=cp.rpv2025!=null&&cp.rpv2026!=null?cp.rpv2026-cp.rpv2025:null;
  var vddD=cp.vdd2025!=null&&cp.vdd2026!=null?cp.vdd2026-cp.vdd2025:null;
  var dddD=cp.ddd2025!=null&&cp.ddd2026!=null?cp.ddd2026-cp.ddd2025:null;
  var npsD=cp.nps2025!=null&&cp.nps2026!=null?cp.nps2026-cp.nps2025:null;
  var lbl_style='color:'+accentColor+';';
  return '<div class="cp-card">'
    +'<div class="cp-lbl" style="'+lbl_style+'">YTD thru '+MO[i]+'</div>'
    +'<div class="dl"><span class="lb">Rev/Day 2025</span><span class="vl">'+fd(cp.rpd2025)+'</span></div>'
    +'<div class="dl"><span class="lb">Rev/Day 2026</span><span class="vl">'+fd(cp.rpd2026)+'</span></div>'
    +'<div class="dl"><span class="lb">&Delta; Rev/Day</span><span class="vl '+dCl+'">'+fd(cp.dRD)+'</span></div>'
    +'<div class="dl"><span class="lb">&Delta; %</span><span class="vl '+dCl+'">'+fp(cp.pctRD)+'</span></div>'
    +'<div class="dl"><span class="lb">$/Visit 2025</span><span class="vl">'+fd(cp.rpv2025)+'</span></div>'
    +'<div class="dl"><span class="lb">$/Visit 2026</span><span class="vl">'+fd(cp.rpv2026)+'</span></div>'
    +(rpvD!=null?'<div class="dl"><span class="lb">&Delta; $/Visit</span><span class="vl '+(rpvD<0?'nc':'pc')+'">'+fd(rpvD)+'</span></div>':'')
    +'<div class="dl"><span class="lb">Vis/DrDay 2025</span><span class="vl">'+fv(cp.vdd2025)+'</span></div>'
    +'<div class="dl"><span class="lb">Vis/DrDay 2026</span><span class="vl">'+fv(cp.vdd2026)+'</span></div>'
    +(vddD!=null?'<div class="dl"><span class="lb">&Delta; Vis/DrDay</span><span class="vl '+(vddD<0?'nc':'pc')+'">'+(vddD<0?'&minus;':'+')+''+Math.abs(vddD.toFixed(2))+'</span></div>':'')
    +'<div class="dl"><span class="lb">Dr Days/Day 2025</span><span class="vl">'+fv(cp.ddd2025)+'</span></div>'
    +'<div class="dl"><span class="lb">Dr Days/Day 2026</span><span class="vl">'+fv(cp.ddd2026)+'</span></div>'
    +(dddD!=null?'<div class="dl"><span class="lb" style="color:#D2691E">&Delta; Dr Days/Day</span><span class="vl" style="color:#D2691E">'+(dddD<0?'&minus;':'+')+''+Math.abs(dddD).toFixed(2)+'</span></div>':'')
    +'<div class="dl"><span class="lb">NPs 2025</span><span class="vl">'+fn(cp.nps2025)+'</span></div>'
    +'<div class="dl"><span class="lb">NPs 2026</span><span class="vl">'+fn(cp.nps2026)+'</span></div>'
    +(npsD!=null?'<div class="dl"><span class="lb">&Delta; NPs</span><span class="vl '+(npsD<0?'nc':'pc')+'">'+(npsD<0?'&minus;':'+')+''+Math.abs(Math.round(npsD)).toLocaleString()+'</span></div>':'')
    +(hasL
      ?'<div class="lev-sec">'
        +'<div class="dl"><span class="lb">$/Visit lever</span><span class="vl" style="color:#C0392B">'+fd(cp.lvVisit)+'</span></div>'
        +'<div class="dl"><span class="lb">Vis/DrDay lever</span><span class="vl" style="color:#7B68EE">'+fd(cp.lvVDD)+'</span></div>'
        +'<div class="dl"><span class="lb">DrDays lever</span><span class="vl" style="color:#D2691E">'+fd(cp.lvDDD)+'</span></div>'
        +'<div class="bar-lbl">Driver mix</div>'
        +'<div class="bar-track">'
        +'<div class="bar-seg" style="width:'+pV.toFixed(1)+'%;background:#C0392B"></div>'
        +'<div class="bar-seg" style="width:'+pVDD.toFixed(1)+'%;background:#7B68EE"></div>'
        +'<div class="bar-seg" style="width:'+pDDD.toFixed(1)+'%;background:#D2691E"></div>'
        +'</div>'
        +'<div class="dom-lbl" style="color:'+domCol+'">Primary: '+domLev+'</div>'
        +'</div>'
      :'<div style="font-size:9px;color:#bbb;font-style:italic;margin-top:4px">Lever N/A</div>')
    +'</div>';
}

function drillHTML(r){
  var cards='';
  for(var i=0;i<r.checkpoints.length;i++)cards+=buildCpCard(r.checkpoints[i],i,'#1F3864');
  return '<div class="drill-inner">'
    +'<div class="drill-title">'+r.office+(r.state&&r.state!=='&mdash;'?' &mdash; '+r.state:'')+'</div>'
    +'<div class="leg-row">'
    +'<span class="leg-item"><span class="leg-sq" style="background:#C0392B"></span>$/Visit lever</span>'
    +'<span class="leg-item"><span class="leg-sq" style="background:#7B68EE"></span>Visits/Dr Day lever</span>'
    +'<span class="leg-item"><span class="leg-sq" style="background:#D2691E"></span>Dr Days/Day lever</span>'
    +'</div>'
    +'<div class="drill-grid">'+cards+'</div>'
    +'</div>';
}

// ── TAB 1 ─────────────────────────────────────────────────────────────────────
function getT1Data(){
  var show=document.getElementById('t1Show').value;
  var state=document.getElementById('t1State').value;
  var search=document.getElementById('t1Search').value.toLowerCase();
  var dir=document.getElementById('t1Dir').value;
  var data=D.slice();
  if(state)data=data.filter(function(r){return r.state===state;});
  if(search)data=data.filter(function(r){return r.office.toLowerCase().indexOf(search)>=0;});
  if(dir!=='all')data=data.filter(function(r){return dirPass(r.checkpoints,dir);});
  // Growing → best improvement first (descending); Declining/All → worst decline first (ascending)
  data.sort(function(a,b){return dir==='grow'?(b.sortDelta||0)-(a.sortDelta||0):(a.sortDelta||0)-(b.sortDelta||0);});
  if(show==='25')data=data.slice(0,25);
  else if(show==='15')data=data.slice(0,15);
  else if(show==='best')data=data.slice().reverse().slice(0,15);
  var showOther=(show==='all')&&!state&&!search&&dir==='all';
  return {data:data,showOther:showOther,show:show,state:state,search:search,dir:dir};
}

function renderT1(){
  t1OpenKey=null;
  var metric=document.getElementById('t1Metric').value;
  var res=getT1Data();
  var data=res.data;

  // KPIs
  var np25=0,np26=0,nps25=0,nps26=0;
  data.forEach(function(r){var cp=lastCp(r.checkpoints);np25+=(cp.np2025||0);np26+=(cp.np2026||0);nps25+=(cp.nps2025||0);nps26+=(cp.nps2026||0);});
  if(res.showOther){var ocp=lastCp(OTHER.checkpoints);np25+=(ocp.np2025||0);np26+=(ocp.np2026||0);nps25+=(ocp.nps2025||0);nps26+=(ocp.nps2026||0);}
  var rpd25=np25/WD25,rpd26=np26/WD26,dRD=rpd26-rpd25,gap=np26-np25,dNP=nps26-nps25;
  sk('t1Kpi25',fk(rpd25),false);
  sk('t1Kpi26',fk(rpd26),rpd26<rpd25);
  sk('t1KpiDelta',fk(dRD),dRD<0);
  sk('t1KpiGap',fmv(gap),gap<0);
  sk('t1KpiNP',(dNP<0?'&minus;':'+')+''+Math.abs(Math.round(dNP)).toLocaleString(),dNP<0);
  var scope=res.state?(' &mdash; '+res.state+(res.search?' | "'+res.search+'"':'')):( res.search?' &mdash; "'+res.search+'"':'');
  document.getElementById('t1Lbl25').innerHTML='Rev/Day 2025'+scope;
  document.getElementById('t1Lbl26').innerHTML='Rev/Day 2026'+scope;
  document.getElementById('t1Mtd').innerHTML=mtdBanner();

  var isFiltered=(res.show!=='all')||res.state||res.search||res.dir!=='all';
  var bar=document.getElementById('t1ScopeBar');
  if(isFiltered){
    var showLabels={all:'All 76',25:'Top 25 declining',15:'Top 15 declining',best:'Top 15 improving'};
    var dirLabels={decl:'Declining',grow:'Growing'};
    var parts=[showLabels[res.show]||res.show];
    if(res.dir!=='all')parts.push(dirLabels[res.dir]||res.dir);
    if(res.state)parts.push(res.state);
    if(res.search)parts.push('"'+res.search+'"');
    bar.style.display='block';
    bar.innerHTML='Showing: <strong>'+parts.join(' &bull; ')+'</strong> &nbsp;&bull;&nbsp; '+data.length+' offices';
  } else {bar.style.display='none';}

  var thead='<thead><tr>'
    +'<th class="rk">#</th>'
    +'<th class="l" style="width:24%">Office</th>'
    +'<th class="l" style="width:8%">State</th>'
    +moHeaders()
    +'</tr></thead>';

  var rows='';
  for(var i=0;i<data.length;i++){
    var r=data[i];
    var cells='';
    for(var j=0;j<r.checkpoints.length;j++){
      var v=metric==='delta'?r.checkpoints[j].dRD:r.checkpoints[j].pctRD;
      var extra='';
      if(j===r.checkpoints.length-1&&metric==='delta'){extra=trendArrow(r.checkpoints);}
      cells+='<td style="'+hcol(v,metric)+'">'+fm(v,metric)+extra+'</td>';
    }
    var key='t1_'+i;
    rows+='<tr class="dr" data-key="'+key+'" data-idx="'+i+'">'
      +'<td class="rk">'+(i+1)+'</td>'
      +'<td class="l">'+r.office+' <span class="arrow" id="a'+key+'">&#8250;</span></td>'
      +'<td class="st">'+r.state+'</td>'+cells
      +'</tr>'
      +'<tr class="drill-wrap" id="d'+key+'" style="display:none"><td colspan="'+(3+MO.length)+'"><div id="dc'+key+'"></div></td></tr>';
  }

  if(res.showOther){
    var r2=OTHER;
    var ocells='';
    for(var j=0;j<r2.checkpoints.length;j++){
      var v2=metric==='delta'?r2.checkpoints[j].dRD:r2.checkpoints[j].pctRD;
      ocells+='<td style="background:#f9f9f9;color:#aaa;font-style:italic">'+fm(v2,metric)+'</td>';
    }
    var okey='t1_other';
    rows+='<tr class="dr other-sep other-row" data-key="'+okey+'" data-idx="-1">'
      +'<td class="rk" style="color:#ccc">&mdash;</td>'
      +'<td class="l" style="color:#999;font-weight:400;font-style:italic">'+r2.office+' <span class="arrow" id="a'+okey+'">&#8250;</span></td>'
      +'<td class="st" style="color:#ccc">'+r2.state+'</td>'+ocells
      +'</tr>'
      +'<tr class="drill-wrap" id="d'+okey+'" style="display:none"><td colspan="'+(3+MO.length)+'"><div id="dc'+okey+'"></div></td></tr>';
  }

  // Pinned company-total row — top of the body, above the first office, not sorted into
  // it. Shown only in the unfiltered full view (same visibility as the Other row); a
  // company-wide total above a filtered subset would misread. Excluded from KPI sum (D
  // + Other already total it) so no double-count.
  var pinned='';
  if(res.showOther&&CONSOLIDATED){
    var rc=CONSOLIDATED,ccells='';
    for(var jc=0;jc<rc.checkpoints.length;jc++){
      var vc=metric==='delta'?rc.checkpoints[jc].dRD:rc.checkpoints[jc].pctRD;
      var extrac=(jc===rc.checkpoints.length-1&&metric==='delta')?trendArrow(rc.checkpoints):'';
      ccells+='<td style="'+hcol(vc,metric)+'">'+fm(vc,metric)+extrac+'</td>';
    }
    var ckey='t1_cons';
    pinned='<tr class="dr" data-key="'+ckey+'" data-idx="-2" style="background:#eef2fa">'
      +'<td class="rk" style="color:#1F3864">&#9733;</td>'
      +'<td class="l" style="font-weight:700;color:#1F3864;border-left:3px solid #1F3864">'+rc.office+' <span class="arrow" id="a'+ckey+'">&#8250;</span></td>'
      +'<td class="st" style="color:#1F3864;font-weight:600">'+rc.state+'</td>'+ccells
      +'</tr>'
      +'<tr class="drill-wrap" id="d'+ckey+'" style="display:none"><td colspan="'+(3+MO.length)+'"><div id="dc'+ckey+'"></div></td></tr>';
  }

  document.getElementById('t1Wrap').innerHTML='<table class="hm">'+thead+'<tbody>'+pinned+rows+'</tbody></table>';

  var trs=document.getElementById('t1Wrap').querySelectorAll('tr.dr');
  var cdata=data;
  for(var k=0;k<trs.length;k++){
    (function(tr,d){
      tr.addEventListener('click',function(){
        var key=tr.getAttribute('data-key');
        var idx=parseInt(tr.getAttribute('data-idx'));
        var r=idx===-1?OTHER:(idx===-2?CONSOLIDATED:d[idx]);
        togT1(key,r);
      });
    })(trs[k],cdata);
  }
}

function togT1(key,r){
  var drill=document.getElementById('d'+key);
  var arr=document.getElementById('a'+key);
  if(!drill||!arr)return;
  var isOpen=drill.style.display!=='none';
  if(t1OpenKey&&t1OpenKey!==key){
    var od=document.getElementById('d'+t1OpenKey);
    var oa=document.getElementById('a'+t1OpenKey);
    if(od)od.style.display='none';
    if(oa)oa.classList.remove('open');
  }
  if(isOpen){drill.style.display='none';arr.classList.remove('open');t1OpenKey=null;}
  else{
    document.getElementById('dc'+key).innerHTML=drillHTML(r);
    drill.style.display='';arr.classList.add('open');t1OpenKey=key;
    drill.scrollIntoView({behavior:'smooth',block:'nearest'});
  }
}

// ── TAB 2 ─────────────────────────────────────────────────────────────────────
function renderT2(){
  t2OpenProv=null;
  document.getElementById('t2Mtd').innerHTML=mtdBanner();
  var officeName=document.getElementById('t2OfficeSel').value;
  var sort=document.getElementById('t2Sort').value;
  var metric=document.getElementById('t2Metric').value;
  var dir=document.getElementById('t2Dir').value;

  if(!officeName){
    document.getElementById('t2Wrap').innerHTML='<div class="empty-state"><div class="icon">&#128101;</div><p>Select an office from the dropdown above to see provider performance</p></div>';
    sk('t2KpiProvs','&mdash;',false);
    sk('t2Kpi25','&mdash;',false);
    sk('t2Kpi26','&mdash;',false);
    sk('t2KpiDelta','&mdash;',false);
    document.getElementById('t2LblOff').innerHTML='Select an office above';
    return;
  }

  var offData=PD_MAP[officeName];
  if(!offData){
    document.getElementById('t2Wrap').innerHTML='<div class="empty-state"><p>No provider data found for this office.</p></div>';
    return;
  }

  var provs=offData.providers.slice();
  if(dir!=='all')provs=provs.filter(function(p){return dirPass(p.checkpoints,dir);});

  var offSummary=null;
  for(var i=0;i<D.length;i++){if(D[i].office===officeName){offSummary=D[i];break;}}
  var dirLabels={decl:' (declining)',grow:' (growing)'};
  if(dir==='all'&&offSummary){
    // No direction filter — show office-summary totals (includes Other providers)
    var cp=lastCp(offSummary.checkpoints);
    sk('t2KpiProvs',offData.providers.length+' named providers',false);
    sk('t2Kpi25',fd(cp.rpd2025),false);
    sk('t2Kpi26',fd(cp.rpd2026),(cp.rpd2026||0)<(cp.rpd2025||0));
    sk('t2KpiDelta',fd(cp.dRD),(cp.dRD||0)<0);
    document.getElementById('t2LblOff').innerHTML=officeName+' &mdash; '+offData.state;
  } else {
    // Direction filter active — recompute Rev/Day from the visible providers
    var np25=0,np26=0;
    provs.forEach(function(p){var c=lastCp(p.checkpoints);np25+=(c.np2025||0);np26+=(c.np2026||0);});
    var rpd25=np25/WD25,rpd26=np26/WD26,dRD=rpd26-rpd25;
    sk('t2KpiProvs',provs.length+' named providers',false);
    sk('t2Kpi25',fd(rpd25),false);
    sk('t2Kpi26',fd(rpd26),rpd26<rpd25);
    sk('t2KpiDelta',fd(dRD),dRD<0);
    document.getElementById('t2LblOff').innerHTML=officeName+' &mdash; '+offData.state+(dirLabels[dir]||'');
  }

  if(!provs.length){
    document.getElementById('t2Wrap').innerHTML='<div class="empty-state"><div class="icon">&#128269;</div><p>No '+(dir==='decl'?'declining':'growing')+' providers at this office</p></div>';
    return;
  }

  if(sort==='delta')provs.sort(function(a,b){return dir==='grow'?(b.sortDelta||0)-(a.sortDelta||0):(a.sortDelta||0)-(b.sortDelta||0);});
  else if(sort==='best')provs.sort(function(a,b){return (b.sortDelta||0)-(a.sortDelta||0);});
  else if(sort==='np25')provs.sort(function(a,b){return (lastCp(b.checkpoints).np2025||0)-(lastCp(a.checkpoints).np2025||0);});
  else if(sort==='np26')provs.sort(function(a,b){return (lastCp(b.checkpoints).np2026||0)-(lastCp(a.checkpoints).np2026||0);});

  var thead='<thead><tr>'
    +'<th class="l" style="width:25%">Provider</th>'
    +moHeaders()
    +'<th>Rev/Day 25</th><th>Rev/Day 26</th><th>&Delta; Rev/Day</th>'
    +'</tr></thead>';

  var rows='';
  for(var i=0;i<provs.length;i++){
    var p=provs[i];
    var cells='';
    for(var j=0;j<p.checkpoints.length;j++){
      var v=metric==='delta'?p.checkpoints[j].dRD:p.checkpoints[j].pctRD;
      var extra='';
      if(j===p.checkpoints.length-1&&metric==='delta'){extra=trendArrow(p.checkpoints);}
      cells+='<td style="'+hcol(v,metric)+';font-size:10px">'+fm(v,metric)+extra+'</td>';
    }
    var rpd25=lastCp(p.checkpoints).rpd2025,rpd26=lastCp(p.checkpoints).rpd2026;
    var drd=rpd25!=null&&rpd26!=null?rpd26-rpd25:null;
    var dCl=(drd||0)<0?'nc':'pc';
    var pkey='t2p'+i;
    var badges='';
    if(p.ptype){
      var bc=p.ptype==='General Dentist'?'badge-gd':(p.ptype==='Hygienist'?'badge-hyg':(p.ptype==='Other'||p.ptype===null?'badge-other':'badge-spec'));
      badges+='<span class="badge '+bc+'">'+p.ptype+'</span>';
    }
    if(p.isNew)badges+='<span class="badge badge-new">NEW</span>';
    rows+='<tr class="dr" data-pkey="'+pkey+'" data-pidx="'+i+'">'
      +'<td class="pname">'+p.provider+badges+' <span class="arrow" id="a'+pkey+'">&#8250;</span></td>'
      +cells
      +'<td style="font-size:10px">'+fd(rpd25)+'</td>'
      +'<td style="font-size:10px">'+fd(rpd26)+'</td>'
      +'<td style="font-size:10px" class="'+dCl+'">'+fd(drd)+'</td>'
      +'</tr>'
      +'<tr class="prov-drill-wrap" id="d'+pkey+'" style="display:none"><td colspan="'+(4+MO.length)+'"><div id="dc'+pkey+'"></div></td></tr>';
  }

  var other=offData.otherProviders;
  if(dir==='all'&&other&&other.count>0&&other.checkpoints.length>0){
    var ocells='';
    for(var j=0;j<other.checkpoints.length;j++){
      var ov=metric==='delta'?other.checkpoints[j].dRD:other.checkpoints[j].pctRD;
      ocells+='<td style="background:#f9f9f9;color:#aaa;font-size:10px;font-style:italic">'+fm(ov,metric)+'</td>';
    }
    rows+='<tr class="other-sep other-row">'
      +'<td class="pname" style="color:#999;font-weight:400;font-style:italic">Other ('+other.count+' providers)</td>'
      +ocells+'<td></td><td></td><td></td></tr>';
  }

  document.getElementById('t2Wrap').innerHTML='<div class="section-lbl">'+officeName+' &mdash; '+provs.length+' named providers</div><table class="pt hm">'+thead+'<tbody>'+rows+'</tbody></table>';

  var trs=document.getElementById('t2Wrap').querySelectorAll('tr.dr');
  var cprovs=provs;
  for(var k=0;k<trs.length;k++){
    (function(tr,ps){
      tr.addEventListener('click',function(){
        var pkey=tr.getAttribute('data-pkey');
        var pidx=parseInt(tr.getAttribute('data-pidx'));
        togT2Prov(pkey,ps[pidx]);
      });
    })(trs[k],cprovs);
  }
}

function togT2Prov(pkey,prov){
  var drill=document.getElementById('d'+pkey);
  var arr=document.getElementById('a'+pkey);
  if(!drill||!arr)return;
  var isOpen=drill.style.display!=='none';
  if(t2OpenProv&&t2OpenProv!==pkey){
    var od=document.getElementById('d'+t2OpenProv);
    var oa=document.getElementById('a'+t2OpenProv);
    if(od)od.style.display='none';
    if(oa)oa.classList.remove('open');
  }
  if(isOpen){drill.style.display='none';arr.classList.remove('open');t2OpenProv=null;}
  else{
    var cards='';
    for(var i=0;i<prov.checkpoints.length;i++)cards+=buildCpCard(prov.checkpoints[i],i,'#5B4A9C');
    var badges2='';
    if(prov.ptype){
      var bc2=prov.ptype==='General Dentist'?'badge-gd':(prov.ptype==='Hygienist'?'badge-hyg':(prov.ptype==='Other'?'badge-other':'badge-spec'));
      badges2+='<span class="badge '+bc2+'">'+prov.ptype+'</span>';
    }
    if(prov.isNew)badges2+='<span class="badge badge-new">NEW</span>';
    var html='<div class="prov-drill-inner">'
      +'<div class="prov-drill-title">'+prov.provider+badges2+'</div>'
      +'<div class="leg-row">'
      +'<span class="leg-item"><span class="leg-sq" style="background:#C0392B"></span>$/Visit lever</span>'
      +'<span class="leg-item"><span class="leg-sq" style="background:#7B68EE"></span>Visits/Dr Day lever</span>'
      +'<span class="leg-item"><span class="leg-sq" style="background:#D2691E"></span>Dr Days/Day lever</span>'
      +'</div>'
      +'<div class="drill-grid">'+cards+'</div>'
      +'</div>';
    document.getElementById('dc'+pkey).innerHTML=html;
    drill.style.display='';arr.classList.add('open');t2OpenProv=pkey;
    drill.scrollIntoView({behavior:'smooth',block:'nearest'});
  }
}

// ── TAB 3 — DOCTOR RANK VIEW ──────────────────────────────────────────────────
// View is locked to the doctor-type universe: General Dentist + dental
// specialists (excludes Hygienist and Other).
var DOCTOR_TYPES={'General Dentist':1,'Prosthodontist':1,'Oral Surgeon':1,'Periodontist':1,'Orthodontist':1,'Pedodontist':1,'Endodontist':1};
var T3_DOCTOR_COUNT=PR_ALL.filter(function(r){return r.ptype&&DOCTOR_TYPES[r.ptype];}).length;
var PR_DOCTORS=PR_ALL.filter(function(r){return r.ptype&&DOCTOR_TYPES[r.ptype];});
function getT3Data(){
  var show=document.getElementById('t3Show').value;
  var state=document.getElementById('t3State').value;
  var search=document.getElementById('t3Search').value.toLowerCase();
  var dir=document.getElementById('t3Dir').value;
  var data=PR_DOCTORS.slice();
  if(dir!=='all')data=data.filter(function(r){return dirPass(r.checkpoints,dir);});
  if(state)data=data.filter(function(r){return r.state===state;});
  if(search)data=data.filter(function(r){
    return r.provider.toLowerCase().indexOf(search)>=0||r.office.toLowerCase().indexOf(search)>=0;
  });
  // Growing → best improvement first (descending); Declining/All → worst decline first (ascending)
  data.sort(function(a,b){return dir==='grow'?(b.sortDelta||0)-(a.sortDelta||0):(a.sortDelta||0)-(b.sortDelta||0);});
  if(show!=='all'){data=data.slice(0,parseInt(show));}
  return {data:data,show:show,state:state,search:search,dir:dir};
}

function renderT3(){
  t3OpenKey=null;
  var metric=document.getElementById('t3Metric').value;
  var res=getT3Data();
  var data=res.data;

  // KPI ribbon — DSO Rev/Day across visible providers
  var np25=0,np26=0;
  data.forEach(function(r){var cp=lastCp(r.checkpoints);np25+=(cp.np2025||0);np26+=(cp.np2026||0);});
  var rpd25=np25/WD25,rpd26=np26/WD26,dRD=rpd26-rpd25;
  document.getElementById('t3Mtd').innerHTML=mtdBanner();
  document.getElementById('t3KpiProvsLbl').innerHTML='Doctors shown';
  document.getElementById('t3ShowAll').textContent='All '+T3_DOCTOR_COUNT+' doctors';
  sk('t3KpiProvs',data.length.toLocaleString(),false);
  sk('t3Kpi25',fk(rpd25),false);
  sk('t3Kpi26',fk(rpd26),rpd26<rpd25);
  sk('t3KpiDelta',fk(dRD),dRD<0);
  var scope=res.state?(' &mdash; '+res.state+(res.search?' | "'+res.search+'"':'')):(res.search?' &mdash; "'+res.search+'"':'');
  document.getElementById('t3Lbl25').innerHTML='DSO Rev/Day 2025'+scope;
  document.getElementById('t3Lbl26').innerHTML='DSO Rev/Day 2026'+scope;

  var isFiltered=(res.show!=='all')||res.state||res.search||res.dir!=='all';
  var bar=document.getElementById('t3ScopeBar');
  if(isFiltered){
    var showLabels={25:'Top 25',50:'Top 50',100:'Top 100',150:'Top 150',all:'All doctors'};
    var dirLabels={decl:'Declining',grow:'Growing'};
    var parts=[showLabels[res.show]||res.show];
    if(res.dir!=='all')parts.push(dirLabels[res.dir]||res.dir);
    if(res.state)parts.push(res.state);
    if(res.search)parts.push('"'+res.search+'"');
    bar.style.display='block';
    bar.innerHTML='Showing: <strong>'+parts.join(' &bull; ')+'</strong> &nbsp;&bull;&nbsp; '+data.length+' providers';
  } else {bar.style.display='none';}

  var thead='<thead><tr>'
    +'<th class="rk">#</th>'
    +'<th class="l" style="width:26%">Provider</th>'
    +'<th class="l" style="width:18%">Office</th>'
    +'<th class="l" style="width:8%">State</th>'
    +moHeaders()
    +'</tr></thead>';

  var rows='';
  for(var i=0;i<data.length;i++){
    var r=data[i];
    var cells='';
    for(var j=0;j<r.checkpoints.length;j++){
      var v=metric==='delta'?r.checkpoints[j].dRD:r.checkpoints[j].pctRD;
      var extra='';
      if(j===r.checkpoints.length-1&&metric==='delta'){extra=trendArrow(r.checkpoints);}
      cells+='<td style="'+hcol(v,metric)+'">'+fm(v,metric)+extra+'</td>';
    }
    var badges='';
    if(r.ptype){
      var bc=r.ptype==='General Dentist'?'badge-gd':(r.ptype==='Hygienist'?'badge-hyg':(r.ptype==='Other'?'badge-other':'badge-spec'));
      badges+='<span class="badge '+bc+'">'+r.ptype+'</span>';
    }
    if(r.isNew)badges+='<span class="badge badge-new">NEW</span>';
    var key='t3_'+i;
    rows+='<tr class="dr" data-key="'+key+'" data-idx="'+i+'">'
      +'<td class="rk">'+(i+1)+'</td>'
      +'<td class="l">'+r.provider+badges+' <span class="arrow" id="a'+key+'">&#8250;</span></td>'
      +'<td class="st">'+r.office+'</td>'
      +'<td class="st">'+r.state+'</td>'+cells
      +'</tr>'
      +'<tr class="prov-drill-wrap" id="d'+key+'" style="display:none"><td colspan="'+(4+MO.length)+'"><div id="dc'+key+'"></div></td></tr>';
  }

  if(!data.length){
    document.getElementById('t3Wrap').innerHTML='<div class="empty-state"><div class="icon">&#128269;</div><p>No providers match the current filters</p></div>';
    return;
  }
  document.getElementById('t3Wrap').innerHTML='<table class="hm">'+thead+'<tbody>'+rows+'</tbody></table>';

  var trs=document.getElementById('t3Wrap').querySelectorAll('tr.dr');
  var cdata=data;
  for(var k=0;k<trs.length;k++){
    (function(tr,d){
      tr.addEventListener('click',function(){
        var key=tr.getAttribute('data-key');
        var idx=parseInt(tr.getAttribute('data-idx'));
        togT3(key,d[idx]);
      });
    })(trs[k],cdata);
  }
}

function togT3(key,r){
  var drill=document.getElementById('d'+key);
  var arr=document.getElementById('a'+key);
  if(!drill||!arr)return;
  var isOpen=drill.style.display!=='none';
  if(t3OpenKey&&t3OpenKey!==key){
    var od=document.getElementById('d'+t3OpenKey);
    var oa=document.getElementById('a'+t3OpenKey);
    if(od)od.style.display='none';
    if(oa)oa.classList.remove('open');
  }
  if(isOpen){drill.style.display='none';arr.classList.remove('open');t3OpenKey=null;}
  else{
    var cards='';
    for(var i=0;i<r.checkpoints.length;i++)cards+=buildCpCard(r.checkpoints[i],i,'#5B4A9C');
    var badges='';
    if(r.ptype){
      var bc=r.ptype==='General Dentist'?'badge-gd':(r.ptype==='Hygienist'?'badge-hyg':(r.ptype==='Other'?'badge-other':'badge-spec'));
      badges+='<span class="badge '+bc+'">'+r.ptype+'</span>';
    }
    if(r.isNew)badges+='<span class="badge badge-new">NEW</span>';
    var html='<div class="prov-drill-inner">'
      +'<div class="prov-drill-title">'+r.provider+badges+' <span style="color:#888;font-weight:400">&mdash; '+r.office+(r.state&&r.state!=='&mdash;'?' ('+r.state+')':'')+'</span></div>'
      +'<div class="leg-row">'
      +'<span class="leg-item"><span class="leg-sq" style="background:#C0392B"></span>$/Visit lever</span>'
      +'<span class="leg-item"><span class="leg-sq" style="background:#7B68EE"></span>Visits/Dr Day lever</span>'
      +'<span class="leg-item"><span class="leg-sq" style="background:#D2691E"></span>Dr Days/Day lever</span>'
      +'</div>'
      +'<div class="drill-grid">'+cards+'</div>'
      +'</div>';
    document.getElementById('dc'+key).innerHTML=html;
    drill.style.display='';arr.classList.add('open');t3OpenKey=key;
    drill.scrollIntoView({behavior:'smooth',block:'nearest'});
  }
}

// ── TAB 4 — DATA SUMMARY (metric-major: office totals + per-metric explode) ───
var T4_METRICS=[
  {key:'np',name:'Net Production',fmt:'money'},{key:'visits',name:'Visits',fmt:'int'},
  {key:'drdays',name:'Doctor Days',fmt:'dec1'},{key:'newpat',name:'New Patients',fmt:'int'},
  {key:'spv',name:'$/Visit',fmt:'money'},{key:'vdd',name:'Vis/DrDay',fmt:'dec2'},
  {key:'rpd',name:'Rev/Day',fmt:'money'}
];
var T4_MO=MO;
var T4_THRESH=10;          // beats/trails-vs-office threshold (percentage points) — single constant for now
var t4Detail='compact';    // compact | full — applies to office + provider rows alike
var t4OpenMetrics={};       // metric name -> exploded

function t4Reset(){t4Detail='compact';t4OpenMetrics={};}
function t4esc(s){return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;');}
function t4f(v,kind){
  if(v==null)return '&mdash;';
  if(kind==='money')return (v<0?'&minus;$':'$')+Math.abs(Math.round(v)).toLocaleString();
  if(kind==='int')return (v<0?'&minus;':'')+Math.abs(Math.round(v)).toLocaleString();
  if(kind==='dec1')return (v<0?'&minus;':'')+Math.abs(v).toLocaleString(undefined,{minimumFractionDigits:1,maximumFractionDigits:1});
  if(kind==='dec2')return (v<0?'&minus;':'')+Math.abs(v).toFixed(2);
  return v;
}
function t4pct(cur,prev){ if(cur==null||prev==null)return null; if(prev<=0)return 'N/M'; return (cur-prev)/prev*100; }
function t4ar(p){return p>=0?'&#9650;':'&#9660;';}                     // ▲ ▼
function t4pctSpan(p){
  if(p==null)return '<span style="color:#bbb">&mdash;</span>';
  if(p==='N/M')return '<span class="nm" title="Not Meaningful — 2025 baseline is zero or negative">N/M</span>';
  return '<span class="'+(p>=0?'t4up':'t4down')+'">'+t4ar(p)+' '+Math.abs(p).toFixed(1)+'%</span>';
}
function t4Entity(metrics){
  function side(y){var o={};for(var k=0;k<T4_METRICS.length;k++){var m=T4_METRICS[k],a=metrics[y][m.key]||[];
    o[m.name]={mo:a.slice(0,Math.max(0,a.length-1)),ytd:a.length>1?a[a.length-1]:null,fmt:m.fmt};}return o;}
  return {y25:side('y1'),y26:side('y2')};
}

/* delta-forward value cell (compact | full); offRef on YTD adds the vs-office reference */
function t4GridCell(cur,prev,kind,isYtd,offRef){
  var p=t4pct(cur,prev),ref='';
  if(offRef!==undefined){
    if(p==='N/M'||p==null||offRef==='N/M'||offRef==null){ref='<div class="gapref num">vs office N/M</div>';}
    else{var gap=p-offRef,beat=gap>=0;
      ref='<div class="gapref num">vs office '+(offRef>=0?'&#9650;':'&#9660;')+Math.abs(offRef).toFixed(1)
        +'% &bull; <span class="'+(beat?'beat':'trail')+'">'+(beat?'+':'&minus;')+Math.abs(gap).toFixed(1)+' pts</span></div>';}
  }
  if(t4Detail==='full'){
    var diff=(cur!=null&&prev!=null)?cur-prev:null;
    var dcls=diff==null?'':(diff>=0?'t4up':'t4down');
    var dstr=diff==null?'&mdash;':((diff>=0?'&#9650; ':'&#9660; ')+t4f(Math.abs(diff),kind));
    return '<td class="cell full'+(isYtd?' ytd':'')+'"><div class="g25 num"><span class="tag">25</span>'+t4f(prev,kind)+'</div>'
      +'<div class="g26 num"><span class="tag">26</span>'+t4f(cur,kind)+'</div>'
      +'<div class="gd num '+dcls+'">'+dstr+'</div>'+ref+'</td>';
  }
  return '<td class="cell'+(isYtd?' ytd':'')+'"><div class="v num">'+t4f(cur,kind)+'</div>'
    +'<div class="d num">'+t4pctSpan(p)+'</div>'+ref+'</td>';
}

/* office header + always-on 7-metric perspective strip (kept pinned via .t4anchor) */
function t4StripHTML(o,off){
  var chips='';
  for(var i=0;i<T4_METRICS.length;i++){
    var m=T4_METRICS[i],nm=m.name,cur=off.y26[nm].ytd,prev=off.y25[nm].ytd,p=t4pct(cur,prev),pill;
    if(p==null)pill='<span style="color:#bbb">&mdash;</span>';
    else if(p==='N/M')pill='<span class="nm">N/M</span>';
    else pill='<span class="pill '+(p>=0?'t4up':'t4down')+'">'+t4ar(p)+' '+Math.abs(p).toFixed(1)+'%</span>';
    chips+='<div class="chip"><div class="m">'+nm+'</div><div class="v num">'+t4f(cur,m.fmt)+'</div>'
      +'<div class="d num">'+pill+'</div><div class="base num">vs '+t4f(prev,m.fmt)+" '25</div></div>";
  }
  var st=(o.state&&o.state!=='—'&&o.state!=='&mdash;')?o.state+' &bull; ':'';
  return '<div class="t4anchor">'
    +'<div class="ohead"><div class="who">'+o.office+' <small>'+st+'office total &bull; '
      +o.providers.length+' named provider'+(o.providers.length===1?'':'s')+'</small></div>'
    +'<div class="ohnote">&#128204; office totals stay pinned &bull; expand a metric for providers</div></div>'
    +'<div class="strip">'+chips+'</div></div>';
}

/* Compact/Full toggle + Expand-all link */
function t4ControlsHTML(){
  var allOpen=T4_METRICS.every(function(m){return t4OpenMetrics[m.name];});
  return '<div class="controls"><span class="lbl">Cell detail</span>'
    +'<div class="seg" id="t4DetailSeg">'
    +'<button type="button" data-detail="compact" class="'+(t4Detail==='compact'?'on':'')+'">Compact</button>'
    +'<button type="button" data-detail="full" class="'+(t4Detail==='full'?'on':'')+'">Full 25&middot;26&middot;&Delta;</button></div>'
    +'<button type="button" class="linkbtn" id="t4ExpandAll">'+(allOpen?'Collapse all metrics &#9650;':'Expand all metrics &#9662;')+'</button></div>';
}

function t4MetricRowCells(ent,m,offRefYtd){
  var b=ent.y26[m.name],a=ent.y25[m.name],cells='';
  for(var j=0;j<b.mo.length;j++)cells+=t4GridCell(b.mo[j],a.mo[j],m.fmt,false,undefined);
  cells+=t4GridCell(b.ytd,a.ytd,m.fmt,true,offRefYtd);
  return cells;
}
function t4AbsChange(ent,nm){var c=ent.y26[nm].ytd,p=ent.y25[nm].ytd;
  if(c==null||p==null)return -Infinity;return Math.abs(c-p);}
function t4FlagHTML(pPct,offDelta){   // 3-state: beats / trails / in-line (every provider labeled)
  if(pPct==='N/M'||pPct==null||offDelta==='N/M'||offDelta==null)
    return '<span class="flag inline" title="2025 baseline non-meaningful">n/m vs office</span>';
  var gap=pPct-offDelta;
  if(Math.abs(gap)>=T4_THRESH){var beat=gap>=0;
    return '<span class="flag '+(beat?'beat':'trail')+'">'+(beat?'&#9650; beats office':'&#9660; trails office')+'</span>';}
  return '<span class="flag inline">&asymp; in line</span>';
}

/* single metric grid: one office-total row per metric (the explode point) + provider rows when open */
function t4BodyHTML(off,officeDelta,provs){
  var head='<th class="lab">Metric / Provider</th>';
  for(var i=0;i<T4_MO.length;i++)head+='<th>'+T4_MO[i]+'</th>';
  head+='<th class="ytd">YTD</th>';
  var body='';
  for(var k=0;k<T4_METRICS.length;k++){
    var m=T4_METRICS[k],nm=m.name,open=!!t4OpenMetrics[nm],hasP=provs.length>0;
    var cnt=!hasP?'no named providers':(open?'showing all providers':'click to expand');
    body+='<tr class="mrow'+(hasP?'':' no-prov')+'" data-m="'+t4esc(nm)+'"'
      +(hasP?' tabindex="0" role="button" aria-expanded="'+(open?'true':'false')+'"':'')+'>'
      +'<td class="lab"><span class="tw">'+(hasP?(open?'&#9662;':'&#9656;'):'&nbsp;')+'</span>'+nm
      +'<span class="cnt">'+cnt+'</span></td>'+t4MetricRowCells(off,m,undefined)+'</tr>';
    if(open&&hasP){
      body+='<tr class="subhead"><td colspan="'+(T4_MO.length+2)+'">Provider contribution to '+nm
        +' &mdash; sorted by who moved the number most</td></tr>';
      var ranked=provs.slice().sort(function(A,B){return t4AbsChange(B.e,nm)-t4AbsChange(A.e,nm);});
      for(var r=0;r<ranked.length;r++){
        var pr=ranked[r],pPct=t4pct(pr.e.y26[nm].ytd,pr.e.y25[nm].ytd);
        body+='<tr class="prov'+(r%2?' alt':'')+'"><td class="pname"><span class="pn">'+pr.name+'</span>'
          +t4FlagHTML(pPct,officeDelta[nm])+(pr.role?'<span class="role">'+pr.role+'</span>':'')+'</td>'
          +t4MetricRowCells(pr.e,m,officeDelta[nm])+'</tr>';
      }
    }
  }
  return '<div class="gridcard"><table class="mg"><thead><tr>'+head+'</tr></thead><tbody>'+body+'</tbody></table></div>';
}

function t4LegendHTML(){
  return '<div class="legend">'
    +'<span><b>&Delta;</b> = 2026 vs 2025 &middot; <span class="t4up">&#9650; up</span> &middot; <span class="t4down">&#9660; down</span> (raw direction)</span>'
    +'<span><b>vs office</b> <span class="beat">&#9650; teal = beating the office</span> &middot; <span class="trail">&#9660; amber = trailing it</span></span>'
    +'<span><b>Flag</b> every provider reads <span class="beat">beats</span> / <span class="trail">trails</span> office (diverges &ge;'
      +T4_THRESH+' pts) or <span style="color:var(--t4-faint)">&asymp; in line</span> &middot; sorted by who moved the number most</span></div>';
}

function t4OfficeOptions(){
  var state=document.getElementById('t4State').value,sel=document.getElementById('t4Office');
  var offices=DS.filter(function(o){return !state||o.state===state;})
    .map(function(o){return o.office;})
    .sort(function(a,b){return a.localeCompare(b,undefined,{sensitivity:'base'});});
  var html='<option value="all">All Offices</option>';
  for(var i=0;i<offices.length;i++)
    html+='<option value="'+t4esc(offices[i])+'">'+offices[i].replace(/&/g,'&amp;')+'</option>';
  sel.innerHTML=html; sel.value=offices.length?offices[0]:'all';   // default to the alphabetically first office in the active state
}

function renderT4(){
  var state=document.getElementById('t4State').value;
  var officeName=document.getElementById('t4Office').value;
  var wrap=document.getElementById('t4Wrap');
  if(!officeName||officeName==='all'){
    wrap.innerHTML='<div class="t4-prompt"><div class="ic">&#127970;</div><p>Select an office'
      +(state?(' in <strong>'+state+'</strong>'):'')+' to see its perspective strip and the metric-by-metric detail.</p></div>';
    return;
  }
  var o=DS_MAP[officeName];
  if(!o){wrap.innerHTML='<div class="t4-prompt"><p>No data for this office.</p></div>';return;}
  var off=t4Entity(o.metrics),officeDelta={};
  for(var i=0;i<T4_METRICS.length;i++){var nm=T4_METRICS[i].name;officeDelta[nm]=t4pct(off.y26[nm].ytd,off.y25[nm].ytd);}
  var provs=o.providers.map(function(p){return {name:p.name,role:p.role||'',e:t4Entity(p.metrics)};});
  wrap.innerHTML=t4StripHTML(o,off)+t4ControlsHTML()+t4BodyHTML(off,officeDelta,provs)+t4LegendHTML();
  t4Bind();
}
function t4Bind(){
  var ds=document.getElementById('t4DetailSeg');
  if(ds)ds.querySelectorAll('button').forEach(function(b){b.addEventListener('click',function(){t4Detail=b.getAttribute('data-detail');renderT4();});});
  var ea=document.getElementById('t4ExpandAll');
  if(ea)ea.addEventListener('click',function(){
    var allOpen=T4_METRICS.every(function(m){return t4OpenMetrics[m.name];});
    if(allOpen)t4OpenMetrics={};else T4_METRICS.forEach(function(m){t4OpenMetrics[m.name]=true;});renderT4();});
  document.querySelectorAll('#tab4 tr.mrow:not(.no-prov)').forEach(function(tr){
    function t(){var nm=tr.getAttribute('data-m');if(t4OpenMetrics[nm])delete t4OpenMetrics[nm];else t4OpenMetrics[nm]=true;renderT4();}
    tr.addEventListener('click',t);
    tr.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();t();}});
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB 5 — MIX SHIFT (procedure composition per 100 visits; consumes the verified
// Build-1 mix_dataset payload — benchmarks rendered as-is, nothing locked recomputed)
// ══════════════════════════════════════════════════════════════════════════════
var MIX=__MIX_DATA__;
var MIXDOLLARS=__MIX_DOLLARS_DATA__;   // View 2: per-(office,provider,group) dollar detail (closed Jan–May, corrected $)
var MG=(MIX.meta&&MIX.meta.groups)||[];        // procedure groups, canonical order (9 tracked + Other)
var MYT=(MIX.meta&&MIX.meta.active_months.length)||MO.length;  // YTD index in per100/visits arrays
var T5_INACTIVE_FRAC=0.05;   // 2026 YTD visits below this fraction of 2025 → activity label (tunable)
// "Other" = residual/bundled category (everything outside the 9 tracked procedures); rendered
// set apart from the 9 (own section, muted shade) — hygienist-driven, NOT a 10th restorative row.
var T5_OTHER=(MIX.meta&&MIX.meta.other_group)||'Other';
var T5_OTHER_LABEL='Other (primarily hygiene / preventive)';
var T5_OTHER_NOTE='Other captures activity outside the 9 tracked procedures — predominantly cleanings/hygiene/preventive at general offices, but includes specialty procedures at surgical and ortho offices. Hygienist-driven in most cases.';
var MG9=MG.filter(function(g){return g!==T5_OTHER;});  // the 9 tracked procedures (Other peeled off)
var T5_HAS_OTHER=MG.indexOf(T5_OTHER)>=0;
// MATCHED window for VOLUME + anchor: the MTD month (June) is full in 2025 but partial in
// 2026 in this source (unlike File A, which truncates it). Comparing them overstates the
// decline, so Volume/anchor use the full matched months (Jan–May) and show June separately.
// Per-100 (Mix) stays Jan–Jun — it's window-invariant (counts & visits scale together).
var T5_MFULL=MYT-(MTD_ON?1:0);                         // # of full matched months (exclude MTD)
var T5_VOLWIN=MO[0]+'&ndash;'+MO[Math.max(0,T5_MFULL-1)];   // e.g. "Jan–May" (Volume window)
var T5_MIXWIN=MO[0]+'&ndash;'+MO[MYT-1];                // e.g. "Jan–Jun" (Mix per-100 window)
function t5jm(a){var s=0;for(var i=0;i<T5_MFULL;i++)s+=a[i];return s;}  // matched-months sum
var T5_PV_MIN=25;   // Procs/Visit guard: a year's matched visits below this -> ratio "n/a" (thin/new base)
var T5_MIX_NOTE='A rising per-100 rate does not mean growth — because total visits fell YoY, the same or fewer procedures spread across fewer visits can raise the rate. When Volume is down but per-100 is up, fewer procedures are being done; the mix tilted toward that one.';

var MIX_BY_OFFICE={};
for(var _mi=0;_mi<(MIX.providers||[]).length;_mi++){var _mp=MIX.providers[_mi];(MIX_BY_OFFICE[_mp.office]=MIX_BY_OFFICE[_mp.office]||[]).push(_mp);}
function t5Prov(office,prov){var l=MIX_BY_OFFICE[office]||[];for(var i=0;i<l.length;i++)if(l[i].provider===prov)return l[i];return null;}

// provider role (General Dentist/Hygienist/…) — carried on PD, not on the mix payload
var T5_ROLE={};
for(var _pi=0;_pi<PD.length;_pi++){var _pod=PD[_pi];for(var _pj=0;_pj<_pod.providers.length;_pj++){var _pp=_pod.providers[_pj];(T5_ROLE[_pod.office]=T5_ROLE[_pod.office]||{})[_pp.provider]=_pp.ptype||'';}}

function t5f1(v){return (v==null)?'<span class="t5muted">&mdash;</span>':v.toFixed(1);}
function t5cnt(v){return (v==null)?'<span class="t5muted">&mdash;</span>':Math.round(v).toLocaleString();}
// VOLUME delta — the HEADLINE: absolute count move (+ %), red down / green up. Counts are
// the truth a rising per-100 can hide, so this leads. Stays real even for departed providers.
function t5DeltaCnt(c25,c26){
  if(c25==null||c26==null)return '<span class="t5vs num">&mdash;</span>';
  var d=Math.round(c26-c25),pct=(c25>0)?((c26-c25)/c25*100):null;
  if(d===0)return '<span class="t5cd num">&plusmn;0</span>';
  var up=d>0,sgn=up?'+':'&minus;';
  return '<span class="t5cd num '+(up?'t5up':'t5down')+'">'+(up?'&#9650;':'&#9660;')+' '+sgn+Math.abs(d).toLocaleString()
    +(pct==null?'':' <small>'+sgn+Math.abs(pct).toFixed(0)+'%</small>')+'</span>';
}
// VISITS anchor — a 3-leg connected story on the Jan–May MATCHED window (full months, both
// years), so it reconciles with the Volume columns: Total Visits, Tracked Procedures (the 9,
// Other EXCLUDED), and Procs/Visit (restorative intensity, dollar-free $/Visit read). June (MTD,
// partial) shown separately. Flat ratio = volume problem; falling ratio = intensity problem.
function t5pvChip(v25,v26){   // count-leg chip — absolute Δ leads (matches Volume columns), % muted
  if(v25==null||v26==null||v25<=0)return '<span class="t5achg t5ana">n/a</span>';
  var d=v26-v25,pct=d/v25*100,down=d<0,up=d>0;
  return '<span class="t5achg '+(down?'t5adown':(up?'t5aup':''))+'">'+(down?'&#9660;':(up?'&#9650;':''))+' '
    +Math.abs(Math.round(d)).toLocaleString()+' <small>('+Math.abs(pct).toFixed(1)+'%)</small></span>';
}
function t5ratioChip(r25,r26){   // ratio Δ — ABSOLUTE leads (3dp), % stays small/secondary
  if(r25==null||r26==null)return '<span class="t5achg t5ana">n/a</span>';
  var d=r26-r25,pct=(r25>0)?(d/r25*100):null;
  if(Math.abs(d)<0.0005)return '<span class="t5achg">&plusmn;0.000</span>';
  var up=d>0,sgn=up?'+':'&minus;';
  return '<span class="t5achg '+(up?'t5aup':'t5adown')+'">'+(up?'&#9650;':'&#9660;')+' '+sgn+Math.abs(d).toFixed(3)
    +(pct==null?'':' <small>'+sgn+Math.abs(pct).toFixed(1)+'%</small>')+'</span>';
}
function t5Anchor(vArr1,vArr2,countsObj){
  var v25=t5jm(vArr1),v26=t5jm(vArr2);
  var tp25=0,tp26=0;   // "Tracked Procedures" leg = the 9 (MG9), Other excluded
  for(var i=0;i<MG9.length;i++){tp25+=t5jm(countsObj[MG9[i]].y1);tp26+=t5jm(countsObj[MG9[i]].y2);}
  // Procs/Visit ratio numerator = ALL-IN (9 tracked + Other) — Other is the largest piece of
  // activity, so all-in is the representative intensity. Other summed with t5jm (Jan–May MATCHED,
  // NOT the Jan–Jun YTD index) so every component shares the same matched window as visits.
  var ap25=tp25,ap26=tp26;
  if(T5_HAS_OTHER){ap25+=t5jm(countsObj[T5_OTHER].y1);ap26+=t5jm(countsObj[T5_OTHER].y2);}
  var r25=(v25>=T5_PV_MIN)?(ap25/v25):null,r26=(v26>=T5_PV_MIN)?(ap26/v26):null;   // thin-base guard
  var win='<span class="t5awin">'+T5_VOLWIN+(MTD_ON?' &middot; matched':'')+'</span>';
  var c0=function(x){return Math.round(x).toLocaleString();};
  function legN(lab,a,b,chip){return '<div class="t5aleg"><span class="t5alab">'+lab+win+'</span>'
    +'<span class="t5anum">'+c0(a)+'<span class="t5aarr">&rarr;</span>'+c0(b)+'</span>'+chip+'</div>';}
  var s='<div class="t5anchor">';
  s+=legN('Total Visits',v25,v26,t5pvChip(v25,v26));
  s+=legN('Tracked Procedures',tp25,tp26,t5pvChip(tp25,tp26));
  s+='<div class="t5aleg"><span class="t5alab">Procs / Visit'+win+'</span><span class="t5anum">'
    +(r25==null?'n/a':r25.toFixed(3))+'<span class="t5aarr">&rarr;</span>'+(r26==null?'n/a':r26.toFixed(3))+'</span>'+t5ratioChip(r25,r26)+'</div>';
  if(MTD_ON){var j25=vArr1[MYT-1],j26=vArr2[MYT-1],jd=j26-j25,jp=(j25>0)?(jd/j25*100):null;
    var jc=(jp==null)?'':' <span class="'+(jd<0?'t5down':'t5up')+'">'+(jd<0?'&#9660;':'&#9650;')+' '+Math.abs(Math.round(jd)).toLocaleString()+' ('+Math.abs(jp).toFixed(0)+'%)</span>';
    s+='<div class="t5asub">'+MO[MYT-1]+' (MTD), partial: '+c0(j25)+' &rarr; '+c0(j26)+jc+' visits &mdash; excluded from the matched YoY</div>';}
  return s+'</div>';
}
var T5_CAP='<div class="t5cap">Volume shows the real direction. A rising per-100 rate isn&rsquo;t growth &mdash; visits fell YoY, so fewer procedures over fewer visits can still raise the rate. Trust the Volume columns for up/down.</div>';
function t5Delta(cur,prev){
  if(cur==null||prev==null)return '<span class="t5vs num">&mdash;</span>';
  var d=cur-prev;
  if(Math.abs(d)<0.05)return '<span class="t5vs num">&plusmn;0.0</span>';
  var up=d>=0;
  return '<span class="t5delta num '+(up?'t5up':'t5down')+'">'+(up?'&#9650;':'&#9660;')+' '+Math.abs(d).toFixed(1)+'</span>';
}
// vs-Company flag — threshold from the mock: in line if |Δ| < 25% of company OR < 1.0
function t5Vs(pv,co){
  if(pv==null||co==null)return '<span class="t5chip in">&mdash;</span>';
  var d=pv-co,a=Math.abs(d);
  if(a<co*0.25||a<1)return '<span class="t5chip in">&asymp; in line</span>';
  return d>0?'<span class="t5chip hi">&#9650; above co</span>':'<span class="t5chip lo">&#9660; below co</span>';
}
// activity status from 2026 vs 2025 YTD visits — visit-based fact, NOT an employment inference
function t5Status(rec){
  var v25=rec.visits.y1[MYT],v26=rec.visits.y2[MYT];
  if(v26===0)return {code:'none',label:'no 2026 activity'};
  if(v25>0&&v26<T5_INACTIVE_FRAC*v25)return {code:'minimal',label:'minimal 2026 activity ('+v26.toLocaleString()+(v26===1?' visit':' visits')+')'};
  return {code:'active',label:''};
}
// aggregate provider records into a benchmark-shaped object (office-scoped landing only;
// State & Company come pre-computed from the data layer and are never recomputed here)
function t5Aggregate(recs){
  var per100={},counts={},visits={y1:[],y2:[]},yk,g;
  for(var y=0;y<2;y++){yk=y?'y2':'y1';for(var i=0;i<=MYT;i++){var vs=0;for(var r=0;r<recs.length;r++)vs+=recs[r].visits[yk][i];visits[yk][i]=vs;}}
  for(var gi=0;gi<MG.length;gi++){g=MG[gi];per100[g]={y1:[],y2:[]};counts[g]={y1:[],y2:[]};
    for(var y2=0;y2<2;y2++){yk=y2?'y2':'y1';for(var j=0;j<=MYT;j++){var c=0;for(var r2=0;r2<recs.length;r2++)c+=recs[r2].counts[g][yk][j];counts[g][yk][j]=c;per100[g][yk][j]=visits[yk][j]>0?(c/visits[yk][j]*100):null;}}
  }
  return {per100:per100,counts:counts,visits:visits};
}

// ① LANDING — consolidated mix for the current scope (company / state / office)
function t5Landing(){
  var state=document.getElementById('t5State').value;
  var office=document.getElementById('t5Office').value;
  var scope,title,sub;
  if(office&&office!=='all'){
    var recs=MIX_BY_OFFICE[office]||[];scope=t5Aggregate(recs);
    // describe the ACTUAL scope shown — the office's real state (from the data), not the dropdown
    var ostate=(recs.length&&recs[0].state)?recs[0].state:'';
    title=office.replace(/&/g,'&amp;');sub=(ostate?ostate+' &middot; ':'')+recs.length+' rendered providers';
  }else if(state){
    scope=MIX.state_benchmark[state];title=state;sub=(scope?scope.n_providers:0)+' rendered providers';
  }else{
    scope=MIX.company_benchmark;title='Company-wide';sub=(scope?scope.n_providers:0)+' rendered providers &middot; all states';
  }
  if(!scope)return '<div class="t5prompt"><div class="ic">&#128138;</div><p>No mix data for this scope.</p></div>';
  // Volume = Jan–May matched (t5jm); per-100 (Mix) = Jan–Jun YTD index (window-invariant)
  function lrow(g,cls,lbl){var c25=t5jm(scope.counts[g].y1),c26=t5jm(scope.counts[g].y2),a=scope.per100[g].y1[MYT],b=scope.per100[g].y2[MYT];
    return '<tr'+(cls?' class="'+cls+'"':'')+'><td class="proc">'+lbl+'</td>'
      +'<td class="num">'+t5cnt(c25)+'</td><td class="num">'+t5cnt(c26)+'</td><td class="num vsep cd2">'+t5DeltaCnt(c25,c26)+'</td>'
      +'<td class="num mx vsep">'+t5f1(a)+'</td><td class="num mx">'+t5f1(b)+'</td><td class="num mx">'+t5Delta(b,a)+'</td></tr>';
  }
  var rows='';
  for(var gi=0;gi<MG9.length;gi++){rows+=lrow(MG9[gi],'',MG9[gi]);}
  if(T5_HAS_OTHER){
    rows+='<tr class="t5sec"><td colspan="7">Preventive / Other</td></tr>';
    rows+=lrow(T5_OTHER,'t5other',T5_OTHER_LABEL+'<span class="t5oinfo" title="'+T5_OTHER_NOTE+'">&#9432;</span>');
  }
  var thead='<thead><tr><th class="lab" rowspan="2">Procedure</th><th class="grpv" colspan="3">Volume (procedures) &middot; '+T5_VOLWIN+'</th><th class="grpm" colspan="3">Mix &middot; per 100 visits &middot; '+T5_MIXWIN+'<span class="t5oinfo" title="'+T5_MIX_NOTE+'">&#9432;</span></th></tr>'
    +'<tr><th>2025</th><th>2026</th><th class="vsep">&Delta;</th><th class="mx vsep">2025</th><th class="mx">2026</th><th class="mx">&Delta;</th></tr></thead>';
  return t5Anchor(scope.visits.y1,scope.visits.y2,scope.counts)
    +'<div class="t5band"><div class="who">'+title+' <small>consolidated mix &middot; material contributors (cum. 90% + 2% floor) &middot; volume '+T5_VOLWIN+' &middot; per 100 visits '+T5_MIXWIN+'</small></div><div class="note">'+sub+'<br>select a provider above to drill in</div></div>'
    +'<table class="t5tbl">'+thead+'<tbody>'+rows+'</tbody></table>'+T5_CAP;
}

// ② COMPACT — the provider's procedures that moved, YoY, vs company
function t5Compact(office,prov){
  var rec=t5Prov(office,prov);
  if(!rec)return '<div class="t5prompt"><p>No mix data for this provider.</p></div>';
  var st=t5Status(rec),inactive=st.code!=='active';
  var role=(T5_ROLE[office]||{})[prov]||'';
  // SORT by biggest VOLUME move (|matched count Δ|, Jan–May) — drivers of the decline lead.
  var procs=MG9.filter(function(g){return (rec.counts[g].y1[MYT]>0)||(rec.counts[g].y2[MYT]>0);})
    .map(function(g){return {g:g,sort:Math.abs(t5jm(rec.counts[g].y2)-t5jm(rec.counts[g].y1))};})
    .sort(function(x,y){return y.sort-x.sort;}).map(function(o){return o.g;});
  function t5Row(g,extraCls,lbl){
    var c25=t5jm(rec.counts[g].y1),c26=t5jm(rec.counts[g].y2);   // Jan–May matched (volume truth)
    var a=rec.per100[g].y1[MYT],b=inactive?null:rec.per100[g].y2[MYT],co=MIX.company_benchmark.per100[g].y2[MYT];
    var s='<tbody>';
    s+='<tr class="t5prov'+(extraCls||'')+'" data-g="'+t4esc(g)+'" tabindex="0" role="button" aria-expanded="false">'
      +'<td class="proc"><span class="tw">&#9656;</span>'+lbl+'</td>'
      +'<td class="num">'+t5cnt(c25)+'</td>'
      +'<td class="num">'+t5cnt(c26)+'</td>'
      +'<td class="num vsep cd2">'+t5DeltaCnt(c25,c26)+'</td>'
      +'<td class="num mx vsep">'+t5f1(a)+'</td>'
      +'<td class="num mx">'+(inactive?'<span class="t5muted">&mdash;</span>':t5f1(b))+'</td>'
      +'<td class="num mx">'+(inactive?'<span class="t5vs">&mdash;</span>':t5Delta(b,a))+'</td>'
      +'<td class="num t5vs vsep">'+t5f1(co)+(inactive?'':' '+t5Vs(b,co))+'</td></tr>';
    s+='<tr class="t5detail" style="display:none"><td colspan="8">'+t5Dollars(office,prov,g)+t5Month(rec,g,st)+'</td></tr>';
    return s+'</tbody>';
  }
  var body='';
  for(var i=0;i<procs.length;i++){body+=t5Row(procs[i],'',procs[i]);}
  // Other rendered set apart (own section, muted shade); NOT ranked into the volume sort
  if(T5_HAS_OTHER&&((rec.counts[T5_OTHER].y1[MYT]>0)||(rec.counts[T5_OTHER].y2[MYT]>0))){
    body+='<tbody><tr class="t5sec"><td colspan="8">Preventive / Other</td></tr></tbody>';
    body+=t5Row(T5_OTHER,' t5other',T5_OTHER_LABEL+'<span class="t5oinfo" title="'+T5_OTHER_NOTE+'">&#9432;</span>');
  }
  var note=inactive?'<div class="t5note">&#9888; <span class="t5inactive">'+st.label+'</span> &mdash; 2026 procedure mix (per-100) is not shown (a visit-based rate is not meaningful here); raw counts still shown. Monthly context on expand.</div>':'';
  var thead='<thead><tr><th class="lab" rowspan="2">Procedure</th><th class="grpv" colspan="3">Volume (procedures) &middot; '+T5_VOLWIN+'</th><th class="grpm" colspan="3">Mix &middot; per 100 visits &middot; '+T5_MIXWIN+'<span class="t5oinfo" title="'+T5_MIX_NOTE+'">&#9432;</span></th><th class="grpm vsep" rowspan="2">Company<br>&rsquo;26</th></tr>'
    +'<tr><th>2025</th><th>2026</th><th class="vsep">&Delta;</th><th class="mx vsep">2025</th><th class="mx">2026</th><th class="mx">&Delta;</th></tr></thead>';
  var band='<div class="t5band"><div class="who">'+prov+' <small>'+office.replace(/&/g,'&amp;')+(rec.state?' &middot; '+rec.state:'')+(role?' &middot; '+role:'')+'</small></div><div class="note">volume '+T5_VOLWIN+' &middot; per 100 visits '+T5_MIXWIN+' &middot; biggest volume move first &middot; click to expand</div></div>';
  return t5Anchor(rec.visits.y1,rec.visits.y2,rec.counts)+band+note+'<table class="t5tbl">'+thead+body+'</table>'+T5_CAP;
}

// ③a EXPANDED — DOLLAR detail for one procedure (View 2). Realization leads (write-off
// rate + net/proc); gross is the muted control. Closed Jan–May matched window, corrected $.
var T5_DOLTAG={collecting:['Collecting less','t5dbad'],billing:['Billing less','t5dwarn'],
  both:['Both','t5dbad'],mix:['Mixed','t5dmut'],
  masked:['Realization &darr; &mdash; masked by gross','t5dwarn'],up:['Realization held','t5dgood']};
function t5dPct(x){return (x==null)?'<span class="t5muted">&mdash;</span>':(x*100).toFixed(1)+'%';}
function t5dPpt(x){if(x==null)return '<span class="t5muted">&mdash;</span>';
  var up=x>0;return '<span class="'+(up?'t5down':(x<0?'t5up':''))+'">'+(up?'+':(x<0?'&minus;':''))+Math.abs(x*100).toFixed(1)+' pt</span>';}
function t5dMoney(x){return (x==null)?'<span class="t5muted">&mdash;</span>':'$'+Math.round(x).toLocaleString();}
function t5dDelMoney(x){if(x==null)return '<span class="t5muted">&mdash;</span>';
  var up=x>=0;return '<span class="'+(up?'t5up':'t5down')+'">'+(up?'+':'&minus;')+'$'+Math.abs(Math.round(x)).toLocaleString()+'</span>';}
function t5Dollars(office,prov,g){
  var m=((MIXDOLLARS[office]||{})[prov]||{})[g];
  if(!m)return '';   // no procedures in window -> no dollar block (honest absence)
  var tg=T5_DOLTAG[m.tag]||['&mdash;','t5dmut'];
  // Δ written-off worse (positive) = red; net/proc down = red. Gross row muted as control.
  return '<div class="t5dwrap t5dol">'
    +'<div class="t5dh t5dolh">Dollars &mdash; realization &middot; closed '+T5_VOLWIN+' &middot; corrected $ '
      +'<span class="t5dtag '+tg[1]+'">'+tg[0]+'</span></div>'
    +'<table class="t5mo t5doltbl"><thead><tr><th class="l">Per procedure</th><th>2025</th><th>2026</th><th>&Delta;</th></tr></thead><tbody>'
    +'<tr class="t5dollead"><td class="l">% written off (Adj &divide; Gross) &mdash; <b>leads</b></td>'
      +'<td class="num">'+t5dPct(m.wo1)+'</td><td class="num">'+t5dPct(m.wo2)+'</td><td class="num">'+t5dPpt(m.dwo)+'</td></tr>'
    +'<tr><td class="l">Net / procedure</td>'
      +'<td class="num">'+t5dMoney(m.np1)+'</td><td class="num">'+t5dMoney(m.np2)+'</td><td class="num">'+t5dDelMoney(m.dnp)+'</td></tr>'
    +'<tr class="t5dolctrl"><td class="l">Gross / procedure <span class="t5dctl">control</span></td>'
      +'<td class="num">'+t5dMoney(m.gp1)+'</td><td class="num">'+t5dMoney(m.gp2)+'</td><td class="num">'+t5dDelMoney(m.dgp)+'</td></tr>'
    +'<tr class="t5dolctrl"><td class="l">Net $ &middot; '+Math.round(m.c1).toLocaleString()+' &rarr; '+Math.round(m.c2).toLocaleString()+' procs</td>'
      +'<td class="num">'+t5dMoney(m.n1)+'</td><td class="num">'+t5dMoney(m.n2)+'</td><td class="num">'+t5dDelMoney((m.n2!=null&&m.n1!=null)?m.n2-m.n1:null)+'</td></tr>'
    +'</tbody></table></div>';
}

// ③ EXPANDED — monthly shape for one procedure: provider / state / company, 2025 & 2026
function t5Month(rec,g,st){
  var state=rec.state,sb=MIX.state_benchmark[state],cb=MIX.company_benchmark,inactive=st.code!=='active';
  function row(cls,lbl,arr,blank){
    var c='';for(var i=0;i<MYT;i++)c+='<td class="num">'+(blank?'<span class="t5muted">&mdash;</span>':t5f1(arr?arr[i]:null))+'</td>';
    return '<tr class="'+cls+'"><td class="l">'+lbl+'</td>'+c+'</tr>';
  }
  function rowC(cls,lbl,arr){   // raw monthly counts — real even when inactive
    var c='';for(var i=0;i<MYT;i++)c+='<td class="num">'+t5cnt(arr?arr[i]:null)+'</td>';
    return '<tr class="'+cls+'"><td class="l">'+lbl+'</td>'+c+'</tr>';
  }
  var glab=(g===T5_OTHER)?T5_OTHER_LABEL:g;
  var h='<tr><th class="l">'+glab+' &middot; by month</th>';
  for(var i=0;i<MYT;i++)h+='<th>'+MO[i]+(MTD_ON&&i===MYT-1?' <span class="t5momtd">MTD</span>':'')+'</th>';
  h+='</tr>';
  var b='';
  b+=rowC('t5cntrow','Provider count 2025',rec.counts[g].y1);
  b+=rowC('t5cntrow','Provider count 2026'+(inactive?' &mdash; '+st.label:''),rec.counts[g].y2);
  b+=row('t5y25 t5sep','Provider /100 2025',rec.per100[g].y1,false);
  b+=row('t5y26','Provider /100 2026'+(inactive?' &mdash; '+st.label:''),rec.per100[g].y2,inactive);
  b+=row('t5bm t5sep','Across '+state+' /100 2025',sb?sb.per100[g].y1:null,false);
  b+=row('t5bm','Across '+state+' /100 2026',sb?sb.per100[g].y2:null,false);
  b+=row('t5bm t5sep','Across Company /100 2025',cb.per100[g].y1,false);
  b+=row('t5bm','Across Company /100 2026',cb.per100[g].y2,false);
  return '<div class="t5dwrap"><div class="t5dh">Monthly shape &mdash; '+glab+' &middot; raw counts then per 100 visits, with state &amp; company context</div><table class="t5mo"><thead>'+h+'</thead><tbody>'+b+'</tbody></table></div>';
}

function t5OfficeOptions(){
  var state=document.getElementById('t5State').value,sel=document.getElementById('t5Office');
  var seen={},uniq=[];
  for(var i=0;i<(MIX.providers||[]).length;i++){var p=MIX.providers[i];if((!state||p.state===state)&&!seen[p.office]){seen[p.office]=1;uniq.push(p.office);}}
  uniq.sort(function(a,b){return a.localeCompare(b,undefined,{sensitivity:'base'});});
  var html='<option value="all">All offices (consolidated)</option>';
  for(var j=0;j<uniq.length;j++)html+='<option value="'+t4esc(uniq[j])+'">'+uniq[j].replace(/&/g,'&amp;')+'</option>';
  sel.innerHTML=html;sel.value='all';
}
function t5ProviderOptions(){
  var office=document.getElementById('t5Office').value,sel=document.getElementById('t5Provider');
  var html='<option value="">&mdash; consolidated (no provider) &mdash;</option>';
  if(office&&office!=='all'){var recs=MIX_BY_OFFICE[office]||[];
    for(var i=0;i<recs.length;i++){var pn=recs[i].provider,rt=(T5_ROLE[office]||{})[pn]||'';
      var lbl=pn.replace(/&/g,'&amp;')+(rt?' &mdash; '+rt:'');   // append provider type; blank type -> name alone
      html+='<option value="'+t4esc(pn)+'">'+lbl+'</option>';}}
  sel.innerHTML=html;sel.value='';
}
function renderT5(){
  var office=document.getElementById('t5Office').value,prov=document.getElementById('t5Provider').value,wrap=document.getElementById('t5Wrap');
  if(prov&&office&&office!=='all'){wrap.innerHTML=t5Compact(office,prov);t5Bind();}
  else{wrap.innerHTML=t5Landing();}
}
function t5Bind(){
  document.querySelectorAll('#tab5 tr.t5prov').forEach(function(tr){
    function tog(){
      var d=tr.parentNode.querySelector('tr.t5detail'),tw=tr.querySelector('.tw');
      if(!d)return;
      var open=d.style.display==='none';
      d.style.display=open?'':'none';
      if(tw)tw.innerHTML=open?'&#9662;':'&#9656;';
      tr.setAttribute('aria-expanded',open?'true':'false');
    }
    tr.addEventListener('click',tog);
    tr.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();tog();}});
  });
}

// ── Tab switching ─────────────────────────────────────────────────────────────
function switchTab(n){
  currentTab=n;
  document.getElementById('tab1').style.display=n===1?'':'none';
  document.getElementById('tab2').style.display=n===2?'':'none';
  document.getElementById('tab3').style.display=n===3?'':'none';
  document.getElementById('tab4').style.display=n===4?'':'none';
  document.getElementById('tab5').style.display=n===5?'':'none';
  var _t6=document.getElementById('tab6'); if(_t6){_t6.style.display=n===6?'':'none';}
  document.getElementById('navTab1').className='nav-tab'+(n===1?' on':'');
  document.getElementById('navTab2').className='nav-tab'+(n===2?' on':'');
  document.getElementById('navTab3').className='nav-tab'+(n===3?' on':'');
  document.getElementById('navTab4').className='nav-tab'+(n===4?' on':'');
  document.getElementById('navTab5').className='nav-tab'+(n===5?' on':'');
  var _n6=document.getElementById('navTab6'); if(_n6){_n6.className='nav-tab'+(n===6?' on':'');}
}

// Realization tab office slicer — show the selected pre-rendered pane (table + KPIs +
// intro + monthly trend all switch together). No-op if the tab isn't present.
function realzPick(v){
  var panes=document.querySelectorAll('.realz-pane');
  for(var i=0;i<panes.length;i++){panes[i].style.display='none';}
  var sel=document.getElementById('rzpane-'+v);
  if(sel){sel.style.display='';}
}
// Realization YoY-table row -> reveal that procedure's monthly Net/proc explode. The
// explode row is pre-rendered as the row's next sibling within THIS pane, so it already
// carries the selected office's data (re-scopes with the slicer for free).
function rzToggle(tr){
  var ex=tr.nextElementSibling;
  if(!ex||!ex.classList.contains('rz-exp')){return;}
  var show=ex.style.display==='none';
  ex.style.display=show?'':'none';
  tr.classList.toggle('rz-open',show);
}

// ── Event listeners ───────────────────────────────────────────────────────────
['t1Show','t1Metric','t1State','t1Dir'].forEach(function(id){document.getElementById(id).addEventListener('change',renderT1);});
document.getElementById('t1Search').addEventListener('input',renderT1);
['t2OfficeSel','t2Sort','t2Metric','t2Dir'].forEach(function(id){document.getElementById(id).addEventListener('change',renderT2);});
['t3Show','t3Metric','t3State','t3Dir'].forEach(function(id){document.getElementById(id).addEventListener('change',renderT3);});
document.getElementById('t3Search').addEventListener('input',renderT3);
document.getElementById('t4State').addEventListener('change',function(){t4Reset();t4OfficeOptions();renderT4();});
document.getElementById('t4Office').addEventListener('change',function(){t4Reset();renderT4();});
document.getElementById('t5State').addEventListener('change',function(){t5OfficeOptions();t5ProviderOptions();renderT5();});
document.getElementById('t5Office').addEventListener('change',function(){t5ProviderOptions();renderT5();});
document.getElementById('t5Provider').addEventListener('change',renderT5);

// ── Init ──────────────────────────────────────────────────────────────────────
renderT1();
renderT3();
t4OfficeOptions();
renderT4();
t5OfficeOptions();
t5ProviderOptions();
renderT5();
</script>
</body>
</html>
"""

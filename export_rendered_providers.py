"""Export the authoritative list of NAMED providers that actually render in the
YoY report — i.e. the material contributors that survive the qualification filter
(cumulative 90% of office production + 2% floor, noise excluded).

This reuses the live pipeline so the export cannot diverge from the report:
  - office set / naming  -> config.OFFICE_LIST (same labels the report renders, == File A)
  - provider set         -> pipeline.build_provider_data() (Provider Deep Dive tab),
                            dropping the "Other (N providers)" rollup (is_other=True)
  - ranking/production    -> peak net production over the active window (max of the two
                            years), the exact figure get_qualifying_providers() sorts on,
                            plus its share of office total.

Run: python3 export_rendered_providers.py
"""
import pandas as pd

import config
import pipeline


def main():
    provider_data = pipeline.build_provider_data()
    _, detail_df = pipeline.load_source_data()

    rows = []
    for office in provider_data:
        oname = office["office"]
        orows = detail_df[detail_df["OFFICE"] == oname]

        # Recompute the exact peak-production figures qualification sorts on, so we
        # can attach production + office-share to each rendered provider.
        clean = orows[~orows["PROVIDER"].apply(pipeline._is_noise)]
        peaks = {}
        for prov, grp in clean.groupby("PROVIDER"):
            np1 = pipeline._safe(grp[grp["year_num"] == config.YEAR_1]["NET PRODUCTION"].sum()) or 0.0
            np2 = pipeline._safe(grp[grp["year_num"] == config.YEAR_2]["NET PRODUCTION"].sum()) or 0.0
            peaks[prov] = max(np1, np2)
        office_total = sum(peaks.values()) or 0.0

        rank = 0
        for prov in office["providers"]:
            if prov.get("is_other"):
                continue  # the "Other (N providers)" rollup is not a named contributor
            rank += 1
            pk = peaks.get(prov["name"], 0.0)
            rows.append({
                "office": oname,
                "state": office["state"],
                "provider": prov["name"],
                "provider_type": prov.get("ptype"),
                "rank_in_office": rank,
                "peak_net_production": round(pk, 2),
                "pct_of_office": round(pk / office_total * 100, 2) if office_total else None,
            })

    df = pd.DataFrame(rows, columns=[
        "office", "state", "provider", "provider_type",
        "rank_in_office", "peak_net_production", "pct_of_office",
    ])

    import os
    out = os.path.join(config._HERE, "output", "Rendered_Providers.xlsx")
    df.to_excel(out, index=False, sheet_name="Rendered_Providers")
    print(f"Rows (office+provider pairs): {len(df)}")
    print(f"Offices represented: {df['office'].nunique()} of {len(config.OFFICE_LIST)}")
    print(f"Saved -> {out}")


if __name__ == "__main__":
    main()

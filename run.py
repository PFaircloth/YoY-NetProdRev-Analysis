import glob
import os
from datetime import datetime

import config
from pipeline import build_office_data, build_provider_data, build_data_summary, build_consolidated
from mix_pipeline import build_mix_dataset
from mix_dollars import build_dollar_dataset
from report import generate_html

_OUTPUT_DIR = os.path.dirname(config.OUTPUT_FILE)
_KEEP = 3


def _cleanup(output_dir, keep):
    files = sorted(
        glob.glob(os.path.join(output_dir, "Revenue_Driver_Analysis_*.html")),
        key=os.path.getmtime,
        reverse=True,
    )
    removed = files[keep:]
    for f in removed:
        os.remove(f)
    if removed:
        print(f"  Removed {len(removed)} old report(s)")


def main():
    os.makedirs(_OUTPUT_DIR, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(_OUTPUT_DIR, f"Revenue_Driver_Analysis_{ts}.html")

    print("Loading source data…")
    office_data   = build_office_data()
    provider_data = build_provider_data()
    data_summary  = build_data_summary()
    mix_dataset   = build_mix_dataset()[0]   # verified Build-1 mix data layer (consume only)
    dollar_dataset = build_dollar_dataset()[0]  # verified procedure-dollar layer (dormant; Phase 2 placement pending)
    consolidated  = build_consolidated()     # company-total pinned row (ties to KPI cards)

    named_offices   = [o for o in office_data if not o["is_other"]]
    total_providers = sum(
        len([p for p in od["providers"] if not p["is_other"]])
        for od in provider_data
    )
    print(f"  {len(named_offices)} offices · {total_providers} named providers")
    print(f"  Mix Shift: {len(mix_dataset['providers'])} providers · "
          f"{len(mix_dataset['meta']['groups'])} procedure groups")

    cons_fin = consolidated["checkpoints"][-1]
    print(f"  Consolidated Rev/Day: {cons_fin['rd25']:,.0f} → {cons_fin['rd26']:,.0f} "
          f"(Δ {cons_fin['drd']:,.0f})")

    print("Generating HTML report…")
    html = generate_html(office_data, provider_data, data_summary, mix_dataset, consolidated,
                         dollar_dataset=dollar_dataset)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = os.path.getsize(output_path) / 1024
    print(f"  Saved → {output_path}  ({size_kb:.0f} KB)")

    _cleanup(_OUTPUT_DIR, _KEEP)


if __name__ == "__main__":
    main()

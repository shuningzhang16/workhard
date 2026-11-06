"""Plot every recorded C-loop sample; never rerun or modify the experiment."""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path

from plot_results import ROOT, decorate, plt, read_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".runs" / ("figure-adc-clear-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = ROOT / "figures/source_data/p1_adc_clear_20261106/overvoltage_c_control_samples.csv"
    rows = read_rows(source)
    fields = ("time_s", "output_v", "measured_output_v", "clear_observable", "duty")
    values = {field: [float(row[field]) for row in rows] for field in fields}
    if not all(math.isfinite(value) for series in values.values() for value in series):
        raise ValueError("Non-finite source data; all source rows retained")
    time = [1000 * value for value in values["time_s"]]
    request = [row for row in rows if row["clear_request"] == "1" and row["clear_result"] == "rejected_unobservable_measurement"]
    if len(request) != 1:
        raise ValueError("Expected the recorded single unobservable clear request")
    clear_ms = 1000 * float(request[0]["time_s"])
    fig, axes = plt.subplots(3, 1, figsize=(183 / 25.4, 135 / 25.4))
    fig.subplots_adjust(left=0.16, right=0.97, bottom=0.13, top=0.83, hspace=0.75)
    decorate(axes)
    axes[0].plot(time, values["output_v"], color="#2476A8", linewidth=1.15, label="Simulated plant voltage")
    axes[0].plot(time, values["measured_output_v"], color="#C16B2A", linewidth=0.9, linestyle="--", label="ADC decoded voltage")
    axes[0].set_ylabel("Output voltage (V)")
    axes[1].step(time, values["clear_observable"], where="post", color="#2476A8", linewidth=1.0)
    axes[1].set(ylabel="Clear bounds valid", ylim=(-0.15, 1.15), yticks=(0, 1))
    axes[2].step(time, values["duty"], where="post", color="#2476A8", linewidth=1.0)
    axes[2].plot(clear_ms, float(request[0]["duty"]), "s", color="#C16B2A", markersize=4, clip_on=False)
    axes[2].set(ylabel="Applied duty", xlabel="Time (ms)", ylim=(-0.02, 0.5))
    for ax in axes:
        ax.set(xlim=(time[0], time[-1]), xticks=(0, 20, 50, 80, 100, 140))
        ax.axvline(clear_ms, color="#767676", linestyle=":", linewidth=0.8)
    fig.suptitle("P1: Incomplete ADC information keeps the fault latched", y=0.975, fontsize=10)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.56, 0.94), ncol=2, frameon=False)
    fig.text(0.5, 0.034, "Actual C core + simulated PWM plant | 80 ms request rejected | All 7,001 samples", ha="center", fontsize=8)
    fig.canvas.draw()
    try:
        from audit_panel_alignment import require_matplotlib_panel_alignment
    except ImportError:
        print("Optional alignment auditor unavailable; no alignment claim.")
    else:
        require_matplotlib_panel_alignment(fig, json_out=args.output / "p1_adc_clear.alignment.json", tolerance_pt=1.5, gutter_tolerance_pt=1.5, require_panel_labels=True, strict=True)
    for suffix in ("svg", "pdf", "png"):
        fig.savefig(args.output / ("p1_adc_clear." + suffix), dpi=300)
    plt.close(fig)
    report = {"source": source.relative_to(ROOT).as_posix(), "rows_read": len(rows), "rows_plotted_per_series": len(rows), "excluded_rows": 0, "time_range_ms": [time[0], time[-1]], "transforms": "seconds to milliseconds only; no smoothing or resampling", "clear_request": request[0], "claim": "Unobservable zero ADC code blocks explicit clear; target ISR and hardware not executed"}
    (args.output / "source_validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "rows": len(rows), "request_ms": clear_ms}))


if __name__ == "__main__":
    main()

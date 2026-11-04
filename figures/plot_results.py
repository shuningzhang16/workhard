"""Plot recorded experiment CSVs without rerunning or modifying the models."""

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(__file__).resolve().parent / "output"
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "DejaVu Sans"],
    "font.size": 8,
    "axes.titlesize": 8,
    "axes.labelsize": 8,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.linewidth": 0.7,
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "savefig.facecolor": "white",
})


def read_rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def decorate(axes):
    for label, ax in zip("abc", axes):
        ax.annotate(label, xy=(0, 1), xycoords="axes fraction",
                    xytext=(-26, 9), textcoords="offset points",
                    fontsize=9, fontweight="bold", annotation_clip=False)
        ax.tick_params(direction="out", length=3, width=0.6)


def save(fig, name):
    OUTPUT.mkdir(exist_ok=True)
    fig.canvas.draw()
    try:
        from audit_panel_alignment import require_matplotlib_panel_alignment
    except ImportError:
        print("Optional panel-alignment auditor is not installed; exporting figure only.")
    else:
        require_matplotlib_panel_alignment(
            fig, json_out=OUTPUT / f"{name}.alignment.json",
            tolerance_pt=1.5, gutter_tolerance_pt=1.5,
            require_panel_labels=True, strict=True,
        )
    fig.savefig(OUTPUT / f"{name}.svg")
    fig.savefig(OUTPUT / f"{name}.pdf")
    fig.savefig(OUTPUT / f"{name}.png", dpi=300)
    plt.close(fig)
    print(f"Saved {name}")


def plot_buck():
    fig, axes = plt.subplots(1, 3, figsize=(183 / 25.4, 80 / 25.4))
    fig.subplots_adjust(left=0.09, right=0.98, bottom=0.22, top=0.71, wspace=0.38)
    titles = ("Startup", "Load: 4 to 2 ohm", "Input: 9 to 7.5 V")
    for ax, case, title in zip(axes, ("startup", "load_step", "input_step"), titles):
        rows = read_rows(ROOT / "experiments/p1-c2000-buck/simulation/results" / f"{case}.csv")
        time_ms = [float(r["time_s"]) * 1000 for r in rows]
        ax.plot(time_ms, [float(r["reference_v"]) for r in rows],
                color="#757575", linestyle="--", linewidth=1.1, label="Reference")
        ax.plot(time_ms, [float(r["output_v"]) for r in rows],
                color="#2476A8", linewidth=1.2, label="Output")
        ax.axvline(20 if case == "startup" else 50, color="#AAAAAA", linestyle=":", linewidth=0.8)
        ax.set(xlim=(0, 100), ylim=(0, 2.5), xlabel="Time (ms)", title=title)
        ax.set_xticks([0, 50, 100])
        ax.set_yticks([0, 1, 2])
    axes[0].set_ylabel("Output voltage (V)")
    decorate(axes)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.55, 0.91),
               ncol=2, frameon=False)
    fig.suptitle("P1: PI response to startup and disturbances", y=0.98, fontsize=10)
    fig.text(0.5, 0.04, "Independent averaged-model simulation | All recorded samples", ha="center", fontsize=8)
    save(fig, "p1_pi_response")


def plot_sps():
    rows = read_rows(ROOT / "experiments/p4-dab/results/scan.csv")
    fig, axes = plt.subplots(1, 2, figsize=(183 / 25.4, 80 / 25.4))
    fig.subplots_adjust(left=0.09, right=0.98, bottom=0.22, top=0.71, wspace=0.30)
    for ratio, color, style in ((0.75, "#767676", "--"), (1.0, "#2476A8", "-"), (1.25, "#C16B2A", "-.")):
        group = sorted((r for r in rows if float(r["voltage_ratio_nV2_over_V1"]) == ratio),
                       key=lambda r: float(r["phase_deg"]))
        phases = [float(r["phase_deg"]) for r in group]
        for ax, metric in zip(axes, ("p2_time_w", "i_rms_a")):
            ax.plot(phases, [float(r[metric]) for r in group], color=color,
                    linestyle=style, marker="o", markersize=2.6, linewidth=1.1,
                    label=f"nV2/V1 = {ratio:g}")
            ax.set(xlim=(-95, 95), xlabel="Phase shift (degrees)")
            ax.set_xticks([-90, -45, 0, 45, 90])
    axes[0].set(ylabel="Transferred power (W)", title="Power direction and magnitude")
    axes[1].set(ylabel="Primary RMS current (A)", title="Current under voltage mismatch", ylim=(0, None))
    decorate(axes)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.55, 0.91),
               ncol=3, frameon=False)
    fig.suptitle("P4: SPS power transfer and circulating current", y=0.98, fontsize=10)
    fig.text(0.5, 0.04, "Ideal periodic simulation | 39 points | No loss or ZVS model", ha="center", fontsize=8)
    save(fig, "p4_sps_transfer")


if __name__ == "__main__":
    plot_buck()
    plot_sps()

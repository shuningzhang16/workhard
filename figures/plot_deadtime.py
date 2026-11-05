"""Illustrate finite deadtime from complete, recorded local-window data."""
import math
from plot_results import ROOT, read_rows, save, plt

def main():
    folder = ROOT / "experiments/p4-dab/results_deadtime_spice"
    rows = read_rows(folder / "eps_weak_long_python.csv")
    time = [float(rows[0]["t0_s"])] + [float(r["t1_s"]) for r in rows]
    voltage = [24 - float(rows[0]["v0_1a_v"])] + [24 - float(r["v1_1a_v"]) for r in rows]
    assert len(rows) == 500
    assert all(math.isfinite(x) for x in time + voltage)
    assert all(a < b for a, b in zip(time, time[1:]))
    short = read_rows(folder / "eps_weak_short_python.csv")[-1]
    short_ns = float(short["t1_s"]) * 1e9
    short_v = 24 - float(short["v1_1a_v"])
    long_ns, long_v = time[-1] * 1e9, voltage[-1]
    fig, ax = plt.subplots(figsize=(183 / 25.4, 90 / 25.4))
    fig.subplots_adjust(left=0.12, right=0.96, bottom=0.25, top=0.84)
    ax.plot([t * 1e9 for t in time], voltage, color="#2476A8", linewidth=1.3)
    ax.axhline(0, color="#888888", linestyle="--", linewidth=0.8)
    ax.plot([short_ns, long_ns], [short_v, long_v], linestyle="none",
            marker="o", markersize=4, color="#C16B2A")
    ax.vlines(short_ns, -2, short_v, color="#AAAAAA", linestyle=":", linewidth=0.7)
    ax.text(174, short_v + 2.6, f"150 ns: {short_v:.2f} V", fontsize=8)
    ax.text(350, 10, f"500 ns: {long_v:.2f} V", fontsize=8)
    ax.vlines(long_ns, long_v, 8.6, color="#AAAAAA", linestyle=":", linewidth=0.7)
    ax.set(xlim=(-5, 525), ylim=(-2, 26), xlabel="Time since turn-off (ns)",
           ylabel="Voltage across incoming upper switch (V)")
    ax.set_xticks([0, 100, 200, 300, 400, 500])
    ax.set_yticks([0, 6, 12, 18, 24])
    fig.suptitle("P4: Residual voltage at the end of a finite deadtime", y=0.95, fontsize=10)
    fig.text(0.5, 0.055,
             "Local EPS window | m = 0.75 | Constant Coss | Ideal-orbit initial current",
             ha="center", fontsize=8)
    save(fig, "p4_local_deadtime")

if __name__ == "__main__":
    main()

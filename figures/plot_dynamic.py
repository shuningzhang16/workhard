"""Plot recorded PWM ripple and DAB reversal; retain all rows of each input CSV."""

from plot_results import ROOT, decorate, plt, read_rows, save


def plot_switching():
    path = ROOT / "experiments/p1-c2000-buck/simulation/switching_results/fixed_duty_0p25us_waveform.csv"
    rows = read_rows(path)
    start = float(rows[0]["time_s"])
    time_us = [(float(row["time_s"]) - start) * 1e6 for row in rows]
    fig, axes = plt.subplots(3, 1, figsize=(183 / 25.4, 120 / 25.4), sharex=True)
    fig.subplots_adjust(left=0.13, right=0.97, bottom=0.14, top=0.88, hspace=0.65)
    series = (
        ([float(r["switch_voltage_v"]) for r in rows], "Switch voltage (V)", "#767676"),
        ([float(r["inductor_current_a"]) for r in rows], "Inductor current (A)", "#C16B2A"),
        ([(float(r["output_v"]) - 2) * 1000 for r in rows], "Output - 2 V (mV)", "#2476A8"),
    )
    for ax, (values, label, color) in zip(axes, series):
        ax.plot(time_us, values, color=color, linewidth=1.0)
        ax.set(ylabel=label, xlim=(0, 400))
    axes[-1].set_xlabel("Time from 59.6 ms (us)")
    decorate(axes)
    fig.suptitle("P1: PWM excitation and steady-state ripple", y=0.97, fontsize=10)
    fig.text(0.5, 0.035, "Ideal switching simulation | All 20 recorded steady-state cycles", ha="center", fontsize=8)
    save(fig, "p1_switching_ripple")


def plot_reversal():
    rows = read_rows(ROOT / "experiments/p4-dab/results_transient/direction_reversal_periods.csv")
    period_ms = (float(rows[1]["t0_s"]) - float(rows[0]["t0_s"])) * 1000
    starts = [float(r["t0_s"]) * 1000 for r in rows]
    edges = starts + [starts[-1] + period_ms]
    centers = [start + period_ms / 2 for start in starts]
    fig, axes = plt.subplots(1, 3, figsize=(183 / 25.4, 80 / 25.4))
    fig.subplots_adjust(left=0.09, right=0.98, bottom=0.22, top=0.71, wspace=0.50)
    axes[0].stairs([float(r["request_deg"]) for r in rows], edges, baseline=None,
                   color="#767676", linestyle="--", linewidth=1.0, label="Requested")
    axes[0].stairs([float(r["scheduled_phase_deg"]) for r in rows], edges, baseline=None,
                   color="#2476A8", linewidth=1.2, label="Scheduled")
    axes[1].plot(centers, [float(r["p2_w"]) for r in rows], color="#2476A8", linewidth=1.2)
    axes[2].plot(centers, [float(r["i_peak_a"]) for r in rows], color="#C16B2A", linewidth=1.2)
    for ax in axes:
        ax.set(xlabel="Time (ms)", xlim=(0, 8))
        ax.set_xticks([0, 4, 8])
        ax.axvline(3, color="#AAAAAA", linestyle=":", linewidth=0.8)
    axes[0].set(ylabel="Phase (degrees)", title="Command and slew limit", ylim=(-40, 40))
    axes[1].set(ylabel="Period mean power (W)", title="Second-side power", ylim=(-25, 25))
    axes[2].set(ylabel="Period peak current (A)", title="Transient current stress", ylim=(0, 1.9))
    decorate(axes)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.55, 0.91), ncol=2, frameon=False)
    fig.suptitle("P4: Phase-command reversal with retained current state", y=0.98, fontsize=10)
    fig.text(0.5, 0.04, "R-L simulation | All 160 periods | No device loss or efficiency model", ha="center", fontsize=8)
    save(fig, "p4_direction_reversal")


if __name__ == "__main__":
    plot_switching()
    plot_reversal()

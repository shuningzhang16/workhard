"""Plot complete recorded control traces, including saturation and signed states."""

from plot_results import ROOT, decorate, plt, read_rows, save


def canvas(title):
    fig, axes = plt.subplots(3, 1, figsize=(183 / 25.4, 135 / 25.4))
    fig.subplots_adjust(left=0.14, right=0.97, bottom=0.13, top=0.85, hspace=0.72)
    decorate(axes)
    fig.suptitle(title, y=0.97, fontsize=10)
    return fig, axes


def plot_protection():
    rows = read_rows(ROOT / "experiments/p1-c2000-buck/simulation/protected_switching_results/overvoltage_control_samples.csv")
    time = [float(r["time_s"]) * 1000 for r in rows]
    fig, axes = canvas("P1: Sampled protection, stored energy and explicit restart")
    axes[0].plot(time, [float(r["reference_v"]) for r in rows], color="#767676",
                 linestyle="--", linewidth=1, label="Reference")
    axes[0].plot(time, [float(r["output_v"]) for r in rows], color="#2476A8",
                 linewidth=1.1, label="Output")
    axes[0].axhline(2.4, color="#C16B2A", linestyle=":", linewidth=0.9, label="Trip threshold")
    axes[0].set_ylabel("Voltage (V)")
    axes[1].plot(time, [float(r["inductor_current_a"]) for r in rows], color="#C16B2A", linewidth=1)
    axes[1].set_ylabel("Inductor current (A)")
    axes[2].step(time, [float(r["duty"]) for r in rows], where="post", color="#2476A8", linewidth=1)
    axes[2].set(ylabel="Duty ratio", xlabel="Time (ms)")
    for ax in axes:
        ax.set(xlim=(0, 140))
        ax.set_xticks([0, 20, 50, 80, 100, 140])
        ax.axvline(50, color="#AAAAAA", linestyle=":", linewidth=0.7)
        ax.axvline(80, color="#AAAAAA", linestyle=":", linewidth=0.7)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.55, 0.93), ncol=3, frameon=False)
    fig.text(0.5, 0.035, "PWM model, 20 us samples | Input fault at 50 ms; explicit clear at 80 ms", ha="center", fontsize=8)
    save(fig, "p1_pwm_protection")


def power_series(ax, rows):
    starts = [int(r["period_index"]) * 0.05 for r in rows]
    edges = starts + [starts[-1] + 0.05]
    ax.stairs([float(r["reference_w"]) for r in rows], edges, baseline=None,
              color="#767676", linestyle="--", linewidth=1, label="Target")
    # Mean power becomes available at the period end, not at its start.
    ax.plot(edges[1:], [float(r["actual_period_p2_w"]) for r in rows],
            color="#2476A8", linewidth=1.1, label="Measured period mean")
    ax.set_ylabel("Power (W)")


def plot_power_loop():
    base = ROOT / "experiments/p4-dab/results_power_loop"
    tracking = read_rows(base / "step_and_reverse_control.csv")
    saturated = read_rows(base / "saturation_return_control.csv")
    fig, axes = canvas("P4: Bidirectional tracking and recovery from power saturation")
    power_series(axes[0], tracking)
    power_series(axes[1], saturated)
    starts = [int(r["period_index"]) * 0.05 for r in saturated]
    edges = starts + [starts[-1] + 0.05]
    for field, label, color, style in (
        ("integral_after_deg", "PI integral", "#C16B2A", "-"),
        ("actual_phase_deg", "Applied phase", "#767676", "--"),
    ):
        axes[2].stairs([float(r[field]) for r in saturated], edges, baseline=None,
                       color=color, linestyle=style, linewidth=1, label=label)
    axes[2].set(ylabel="Angle (degrees)", xlabel="Time (ms)")
    axes[2].legend(loc="upper right", frameon=False, ncol=2)
    for ax in axes:
        ax.set(xlim=(0, 16))
        ax.set_xticks([0, 4, 8, 12, 16])
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.55, 0.93), ncol=2, frameon=False)
    fig.text(0.5, 0.035, "Fixed-bus R-L simulation | 50 us updates | All 300 / 320 recorded periods", ha="center", fontsize=8)
    save(fig, "p4_power_loop")


if __name__ == "__main__":
    plot_protection()
    plot_power_loop()

"""Continuous SPS/EPS periods with RLC dead time and explicit turn-on charge.

Open-loop finite physics experiment. It does not replace the sampled-protection
or PI demonstrations. Only the initial run state is supplied; edge current is
never taken from a periodic ideal waveform after initialization.
"""

from dataclasses import dataclass
import math

from dab_deadtime import Device, LEGS, edge_windows, simulate_window
from dab_eps import simulate_eps
from dab_transient import rl_step


@dataclass
class ContinuousRun:
    rows: list
    periods: list
    turnons: list


def simulate_continuous(parameters, alpha_deg, phase_deg, *, deadtime_s=150e-9,
                        resistance_ohm=0.5, period_count=100, initial_current_a=0.0,
                        device=None, deadtime_step_s=None):
    """Advance all events in order, using exact RL outside dead-time windows.

    The ideal cycle supplies switching TIMES only. Its currents are discarded.
    Time zero is shifted to its first scheduled turn-off edge, so each period
    contains complete dead-time windows and the following active intervals.
    A turn-on is a zero-duration capacitor charge redistribution: iL remains
    unchanged, source charge and C*(v_before-v_target)^2 loss are both recorded.
    """
    device = device or Device()
    if resistance_ohm <= 0 or period_count < 1 or not math.isfinite(initial_current_a):
        raise ValueError("Require positive resistance/period count and finite initial current")
    schedule = edge_windows(simulate_eps(parameters, alpha_deg, phase_deg), alpha_deg)
    time_origin = schedule[0]["edge_time_s"]
    if any(not 0 < deadtime_s < w["next_edge_gap_s"] for w in schedule):
        raise ValueError("Dead time must finish before the next scheduled edge")
    buses = (parameters.v1_v, parameters.v1_v, parameters.v2_v, parameters.v2_v)
    factors = (1.0, -1.0, -parameters.turns_ratio, parameters.turns_ratio)
    nodes = [q * bus for q, bus in zip(schedule[0]["before"], buses)]
    current, time = initial_current_a, 0.0
    period = 1 / parameters.frequency_hz
    rows, periods, turnons = [], [], []
    cumulative_source = cumulative_losses = 0.0

    def stored(i, v):
        return 0.5 * parameters.inductance_h * i * i + math.fsum(
            0.5 * device.coss_f * (x*x + (bus-x)**2) for x, bus in zip(v, buses))

    initial_energy = stored(current, nodes)

    def append(kind, stop, end_i, end_nodes, e1, e2, er, ed, eon, charge, integral_i2, peak, edge_index=-1):
        nonlocal current, nodes, time, cumulative_source, cumulative_losses
        before_e, after_e = stored(current, nodes), stored(end_i, end_nodes)
        cumulative_source += e1 + e2
        cumulative_losses += er + ed + eon
        row = {"period_index": k, "kind": kind, "edge_index": edge_index,
            "t0_s": time, "t1_s": stop, "i0_a": current, "i1_a": end_i,
            "source1_energy_j": e1, "source2_energy_j": e2,
            "resistor_energy_j": er, "diode_energy_j": ed,
            "turnon_redistribution_energy_j": eon, "inductor_charge_c": charge,
            "integral_i2_a2_s": integral_i2, "i_peak_a": peak,
            "stored_energy0_j": before_e, "stored_energy1_j": after_e,
            "energy_residual_j": e1 + e2 - er - ed - eon - (after_e - before_e),
            "cumulative_energy_residual_j": cumulative_source - cumulative_losses - (after_e - initial_energy)}
        for j, leg in enumerate(LEGS):
            row[f"v0_{leg}_v"], row[f"v1_{leg}_v"] = nodes[j], end_nodes[j]
        rows.append(row)
        current, nodes, time = end_i, list(end_nodes), stop

    def active_until(stop):
        if stop <= time:
            return
        voltage1 = nodes[0] - nodes[1]
        voltage2 = parameters.turns_ratio * (nodes[2] - nodes[3])
        end_i, charge, i2 = rl_step(current, voltage1 - voltage2, stop - time,
                                  parameters.inductance_h, resistance_ohm)
        append("active_RL", stop, end_i, nodes, voltage1 * charge, -voltage2 * charge,
               resistance_ohm * i2, 0.0, 0.0, charge, i2, max(abs(current), abs(end_i)))

    for k in range(period_count):
        first_row, first_turnon = len(rows), len(turnons)
        start_current = current
        for edge_index, scheduled in enumerate(schedule):
            start = k * period + (scheduled["edge_time_s"] - time_origin)
            active_until(start)
            before = [q * bus for q, bus in zip(scheduled["before"], buses)]
            if nodes != before:
                raise AssertionError("Scheduled gate state differs from the continuous node state")
            window = {**scheduled, "initial_current_a": current}
            local_rows, events = simulate_window(window, deadtime_s, device=device,
                resistance_ohm=resistance_ohm, sample_step_s=deadtime_step_s or deadtime_s)
            for r in local_rows:
                end_nodes = [r[f"v1_{leg}_v"] for leg in LEGS]
                append("deadtime_RLC", start + r["t1_s"], r["i1_a"], end_nodes,
                    r["source1_energy_j"], r["source2_energy_j"], r["resistor_energy_j"],
                    r["diode_energy_j"], 0.0, r["inductor_charge_c"], r["integral_i2_a2_s"], r["i_peak_a"], edge_index)
            target_nodes = list(nodes)
            source_jump = [0.0, 0.0]
            turnon_energy = 0.0
            for event, j in zip(events, scheduled["switched"]):
                target = scheduled["after"][j] * buses[j]
                delta_v = target - nodes[j]
                supplied = device.coss_f * buses[j] * delta_v * (1 if scheduled["after"][j] else -1)
                dissipated = device.coss_f * delta_v ** 2
                source_jump[j // 2] += supplied
                turnon_energy += dissipated
                target_nodes[j] = target
                turnons.append({"period_index": k, "edge_index": edge_index, "t_s": time,
                    **event, "i_after_turnon_a": current, "node_after_turnon_v": target,
                    "source_jump_energy_j": supplied, "turnon_redistribution_energy_j": dissipated,
                    "accounting_note": "pair-capacitor loss; residual_coss_energy_j is diagnostic only, not added"})
            append("turnon_charge", time, current, target_nodes, *source_jump,
                   0.0, 0.0, turnon_energy, 0.0, 0.0, abs(current), edge_index)
        active_until((k + 1) * period)
        period_rows, period_turnons = rows[first_row:], turnons[first_turnon:]
        totals = {key: math.fsum(r[key] for r in period_rows) for key in (
            "source1_energy_j", "source2_energy_j", "resistor_energy_j", "diode_energy_j",
            "turnon_redistribution_energy_j", "inductor_charge_c", "integral_i2_a2_s")}
        change = period_rows[-1]["stored_energy1_j"] - period_rows[0]["stored_energy0_j"]
        periods.append({"period_index": k, "i_start_a": start_current, "i_end_a": current,
            "periodic_current_difference_a": current - start_current,
            "p1_input_w": totals["source1_energy_j"] / period,
            "p2_output_w": -totals["source2_energy_j"] / period,
            "resistor_power_w": totals["resistor_energy_j"] / period,
            "diode_power_w": totals["diode_energy_j"] / period,
            "turnon_redistribution_power_w": totals["turnon_redistribution_energy_j"] / period,
            "i_rms_a": math.sqrt(totals["integral_i2_a2_s"] / period),
            "i_mean_a": totals["inductor_charge_c"] / period,
            "i_peak_a": max(r["i_peak_a"] for r in period_rows),
            "zvs_in_model": sum(e["zvs_in_this_model"] for e in period_turnons),
            "leg_turnons": len(period_turnons), "stored_energy_change_j": change,
            "energy_residual_j": totals["source1_energy_j"] + totals["source2_energy_j"] -
                totals["resistor_energy_j"] - totals["diode_energy_j"] - totals["turnon_redistribution_energy_j"] - change,
            "integration_segments": len(period_rows)})
    return ContinuousRun(rows, periods, turnons)

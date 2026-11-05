"""Coupled L + eight linear output capacitors during one dead-time window.

Each window starts with the supplied ideal-cycle edge current. Other edges
are not replayed or reset within that window. This is a local commutation
experiment, not a dead-time-corrected periodic DAB operating point.
"""

from dataclasses import dataclass
import math

from dab_eps import gate_states


LEGS = ("1a", "1b", "2a", "2b")
GATES = ("q1a_high", "q1b_high", "q2a_high", "q2b_high")


@dataclass
class Device:
    # TI CSD18540Q5B, SLPS488B p.3: Qoss typ 83 nC at 30 V.
    # Constant charge-equivalent C is a teaching assumption outside that anchor.
    coss_f: float = 83e-9 / 30.0
    diode_drop_v: float = 0.8  # Typ at 28 A, NOT a fitted low-current diode curve.


def edge_windows(cycle, alpha_deg):
    """Group simultaneous leg edges; retain their shared inductor state."""
    windows = []
    p = cycle.parameters
    for index, segment in enumerate(cycle.segments):
        previous = cycle.segments[index - 1]
        before = gate_states((previous.t0_s + previous.t1_s) * p.frequency_hz / 2,
                             alpha_deg, cycle.phase_deg)
        after = gate_states((segment.t0_s + segment.t1_s) * p.frequency_hz / 2,
                            alpha_deg, cycle.phase_deg)
        switched = [j for j, key in enumerate(GATES) if before[key] != after[key]]
        if switched:
            windows.append({"edge_time_s": segment.t0_s, "parameters": p,
                            "before": [before[key] for key in GATES],
                            "after": [after[key] for key in GATES],
                            "switched": switched, "initial_current_a": segment.i0_a})
    for index, window in enumerate(windows):
        next_time = windows[index + 1]["edge_time_s"] if index + 1 < len(windows) else windows[0]["edge_time_s"] + 1 / p.frequency_hz
        window["next_edge_gap_s"] = next_time - window["edge_time_s"]
    return windows


def mode_advance(current, nodes, factors, free, dt, inductance, capacitance):
    """Exact unclamped LC solution for one fixed set of free nodes.

    Returns current, node voltages and independently integrated inductor charge.
    R is zero here, consistent with the source ideal periodic waveforms.
    """
    voltage = math.fsum(a * v for a, v in zip(factors, nodes))
    stiffness = math.fsum(factors[j] ** 2 / (2 * capacitance) for j in free)
    if stiffness:
        omega = math.sqrt(stiffness / inductance)
        theta = omega * dt
        sine, cosine = math.sin(theta), math.cos(theta)
        one_minus_cos = 2 * math.sin(theta / 2) ** 2
        end_current = current * cosine + voltage / (inductance * omega) * sine
        charge = current * sine / omega + voltage / stiffness * one_minus_cos
    else:
        end_current = current + voltage / inductance * dt
        charge = current * dt + voltage / inductance * dt * dt / 2
    end_nodes = list(nodes)
    for j in free:
        end_nodes[j] -= factors[j] * charge / (2 * capacitance)
    return end_current, end_nodes, charge


def simulate_window(window, deadtime_s, *, device=None, sample_step_s=1e-9):
    device = device or Device()
    p = window["parameters"]
    if not 0 < deadtime_s < window["next_edge_gap_s"]:
        raise ValueError("Local dead time must end before the next scheduled edge")
    if device.coss_f <= 0 or device.diode_drop_v < 0 or sample_step_s <= 0:
        raise ValueError("Require positive capacitance/step and nonnegative diode drop")
    factors = (1.0, -1.0, -p.turns_ratio, p.turns_ratio)
    buses = (p.v1_v, p.v1_v, p.v2_v, p.v2_v)
    nodes = [q * bus for q, bus in zip(window["before"], buses)]
    current = window["initial_current_a"]
    low = -device.diode_drop_v
    highs = [bus + device.diode_drop_v for bus in buses]
    switched = window["switched"]
    rows = []
    time = source_energy = diode_energy = 0.0
    reached = {j: None for j in switched}

    def stored(i, v):
        return 0.5 * p.inductance_h * i * i + math.fsum(
            0.5 * device.coss_f * (x * x + (bus - x) ** 2) for x, bus in zip(v, buses))

    initial_energy = stored(current, nodes)
    while time < deadtime_s - 1e-20:
        # At a zero-current crossing, use its physical slope to choose release.
        direction = current if abs(current) > 1e-12 else math.fsum(a * v for a, v in zip(factors, nodes))
        free, clamped = [], []
        for j in switched:
            velocity_sign = -factors[j] * direction
            if (nodes[j] <= low + 1e-9 and velocity_sign <= 0) or (
                    nodes[j] >= highs[j] - 1e-9 and velocity_sign >= 0):
                clamped.append(j)
            else:
                free.append(j)
        dt = min(sample_step_s, deadtime_s - time)
        candidate_i, candidate_v, _ = mode_advance(current, nodes, factors, free, dt, p.inductance_h, device.coss_f)
        hits = []
        for j in free:
            if candidate_v[j] < low:
                hits.append(("node", j, low))
            elif candidate_v[j] > highs[j]:
                hits.append(("node", j, highs[j]))
        if current * candidate_i < 0 and abs(current) > 1e-12:
            hits.append(("current", -1, 0.0))
        event = None
        # Resolve diode activation and current reversal before advancing state.
        for kind, j, boundary in hits:
            left, right = 0.0, dt
            start_value = current if kind == "current" else nodes[j] - boundary
            for _ in range(36):
                mid = (left + right) / 2
                mi, mv, _ = mode_advance(current, nodes, factors, free, mid, p.inductance_h, device.coss_f)
                value = mi if kind == "current" else mv[j] - boundary
                if start_value * value > 0:
                    left = mid
                else:
                    right = mid
            if event is None or right < event[0]:
                event = (right, kind, j, boundary)
        if event:
            dt = event[0]
        end_i, end_v, charge = mode_advance(current, nodes, factors, free, dt, p.inductance_h, device.coss_f)
        if event:
            if event[1] == "current":
                end_i = 0.0
            else:
                end_v[event[2]] = event[3]
        source_coeff = 0.0
        for j in range(4):
            if j in free:
                source_coeff += buses[j] * factors[j] / 2
            elif (j in clamped and nodes[j] > buses[j]) or (j not in switched and window["before"][j]):
                source_coeff += buses[j] * factors[j]
        diode_coeff = device.diode_drop_v * sum(abs(factors[j]) for j in clamped)
        supplied, dissipated = source_coeff * charge, diode_coeff * abs(charge)
        source_energy += supplied
        diode_energy += dissipated
        start_e, end_e = stored(current, nodes), stored(end_i, end_v)
        row = {"t0_s": time, "t1_s": time + dt, "i0_a": current, "i1_a": end_i,
               "free_legs": ":".join(LEGS[j] for j in free),
               "clamped_legs": ":".join(LEGS[j] for j in clamped),
               "inductor_charge_c": charge, "source_energy_j": supplied, "diode_energy_j": dissipated,
               "stored_energy0_j": start_e, "stored_energy1_j": end_e,
               "energy_residual_j": supplied - dissipated - (end_e - start_e),
               "cumulative_energy_residual_j": source_energy - diode_energy - (end_e - initial_energy),
               "source_power0_w": source_coeff * current, "source_power1_w": source_coeff * end_i,
               "diode_power0_w": diode_coeff * abs(current), "diode_power1_w": diode_coeff * abs(end_i)}
        for j, leg in enumerate(LEGS):
            row[f"v0_{leg}_v"], row[f"v1_{leg}_v"] = nodes[j], end_v[j]
        rows.append(row)
        for j in switched:
            target = buses[j] if window["after"][j] else 0.0
            vds0 = target - nodes[j] if window["after"][j] else nodes[j]
            vds1 = target - end_v[j] if window["after"][j] else end_v[j]
            if reached[j] is None and vds1 <= 0:
                # Locate the rail crossing with the same exact free-mode solution.
                left, right = 0.0, dt
                for _ in range(36):
                    mid = (left + right) / 2
                    _, mv, _ = mode_advance(current, nodes, factors, free, mid, p.inductance_h, device.coss_f)
                    mvds = target - mv[j] if window["after"][j] else mv[j]
                    if mvds > 0:
                        left = mid
                    else:
                        right = mid
                reached[j] = time + right if vds0 > 0 else time
        time += dt
        current, nodes = end_i, end_v
    events = []
    for j in switched:
        vds = buses[j] - nodes[j] if window["after"][j] else nodes[j]
        target_clamped = (nodes[j] >= highs[j] - 1e-9 if window["after"][j] else nodes[j] <= low + 1e-9)
        events.append({"leg": LEGS[j], "incoming": "high" if window["after"][j] else "low",
            "iL_initial_a": window["initial_current_a"], "iL_turnon_a": current,
            "initial_directional_current_a": -(window["after"][j] - window["before"][j]) * factors[j] * window["initial_current_a"],
            "node_at_turnon_v": nodes[j], "incoming_vds_at_turnon_v": vds,
            "first_target_rail_time_s": "" if reached[j] is None else reached[j],
            "target_diode_clamped_at_turnon": int(target_clamped),
            "zvs_in_this_model": int(vds <= 1e-6),  # Numerical rail tolerance, not device spec.
            "residual_coss_energy_j": 0.5 * device.coss_f * max(vds, 0) ** 2})
    return rows, events

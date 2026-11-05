"""Coupled L + eight linear output capacitors during one dead-time window.

Each window starts with the supplied ideal-cycle edge current. Other edges
are not replayed or reset within that window. This is a local commutation
experiment, not a dead-time-corrected periodic DAB operating point.
"""

from dataclasses import dataclass
import math

from dab_eps import gate_states
from dab_transient import rl_step


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


def mode_advance(current, nodes, factors, free, dt, inductance, capacitance, resistance=0.0):
    """Exact unclamped LC solution for one fixed set of free nodes.

    Returns current, node voltages and independently integrated inductor charge.
    R defaults to zero for the original local experiments. The damped branch
    is limited to underdamped modes used by the finite full-cycle experiments.
    """
    voltage = math.fsum(a * v for a, v in zip(factors, nodes))
    stiffness = math.fsum(factors[j] ** 2 / (2 * capacitance) for j in free)
    if stiffness and resistance:
        decay_rate = resistance / (2 * inductance)
        omega2 = stiffness / inductance - decay_rate ** 2
        if omega2 <= 0:
            raise ValueError("This commutation model supports underdamped free-node modes")
        omega = math.sqrt(omega2)
        theta = omega * dt
        decay, sine, cosine = math.exp(-decay_rate * dt), math.sin(theta), math.cos(theta)
        end_current = decay * (current * cosine + (voltage / inductance - decay_rate * current) / omega * sine)
        # W(t)=sum(a*v), W'=-stiffness*i. expm1 avoids cancellation near t=0.
        one_minus_decay_cos = -math.expm1(-decay_rate * dt) + decay * 2 * math.sin(theta / 2) ** 2
        charge = (voltage * one_minus_decay_cos - decay * (decay_rate * voltage - stiffness * current) / omega * sine) / stiffness
    elif stiffness:
        omega = math.sqrt(stiffness / inductance)
        theta = omega * dt
        sine, cosine = math.sin(theta), math.cos(theta)
        one_minus_cos = 2 * math.sin(theta / 2) ** 2
        end_current = current * cosine + voltage / (inductance * omega) * sine
        charge = current * sine / omega + voltage / stiffness * one_minus_cos
    elif resistance:
        end_current, charge, _ = rl_step(current, voltage, dt, inductance, resistance)
    else:
        end_current = current + voltage / inductance * dt
        charge = current * dt + voltage / inductance * dt * dt / 2
    end_nodes = list(nodes)
    for j in free:
        end_nodes[j] -= factors[j] * charge / (2 * capacitance)
    return end_current, end_nodes, charge


def mode_current_integrals(current, nodes, factors, free, dt, inductance, capacitance, resistance):
    """Independent Gauss quadrature of i^2 and analytical extrema in a mode.

    The analytic step is limited to at most pi/4 resonant angle by the caller.
    No energy-balance subtraction is used to obtain resistor dissipation.
    """
    quadrature = ((-0.8611363115940526, 0.3478548451374538),
                  (-0.3399810435848563, 0.6521451548625461),
                  (0.3399810435848563, 0.6521451548625461),
                  (0.8611363115940526, 0.3478548451374538))
    integral_i2 = dt / 2 * math.fsum(weight * mode_advance(current, nodes, factors, free,
        dt * (1 + position) / 2, inductance, capacitance, resistance)[0] ** 2 for position, weight in quadrature)
    end_i = mode_advance(current, nodes, factors, free, dt, inductance, capacitance, resistance)[0]
    peak = max(abs(current), abs(end_i))
    if free:
        stiffness = math.fsum(factors[j] ** 2 / (2 * capacitance) for j in free)
        decay_rate = resistance / (2 * inductance)
        omega = math.sqrt(stiffness / inductance - decay_rate ** 2)
        voltage = math.fsum(a * v for a, v in zip(factors, nodes))
        sine_coefficient = (voltage / inductance - decay_rate * current) / omega
        dcos = omega * sine_coefficient - decay_rate * current
        dsin = -omega * current - decay_rate * sine_coefficient
        root = math.atan2(-dcos, dsin) % math.pi
        if 0 < root < omega * dt:
            peak = max(peak, abs(mode_advance(current, nodes, factors, free, root / omega,
                                             inductance, capacitance, resistance)[0]))
    return integral_i2, peak


def simulate_window(window, deadtime_s, *, device=None, sample_step_s=1e-9, resistance_ohm=0.0):
    device = device or Device()
    p = window["parameters"]
    if not 0 < deadtime_s < window["next_edge_gap_s"]:
        raise ValueError("Local dead time must end before the next scheduled edge")
    if device.coss_f <= 0 or device.diode_drop_v < 0 or sample_step_s <= 0:
        raise ValueError("Require positive capacitance/step and nonnegative diode drop")
    if not math.isfinite(resistance_ohm) or resistance_ohm < 0:
        raise ValueError("Series resistance must be finite and nonnegative")
    factors = (1.0, -1.0, -p.turns_ratio, p.turns_ratio)
    buses = (p.v1_v, p.v1_v, p.v2_v, p.v2_v)
    nodes = [q * bus for q, bus in zip(window["before"], buses)]
    current = window["initial_current_a"]
    low = -device.diode_drop_v
    highs = [bus + device.diode_drop_v for bus in buses]
    switched = window["switched"]
    rows = []
    time = source_energy = diode_energy = resistor_energy = 0.0
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
        if free:
            omega0 = math.sqrt(sum(factors[j] ** 2 for j in free) / (2 * device.coss_f * p.inductance_h))
            dt = min(dt, math.pi / (4 * omega0))
        candidate_i, candidate_v, _ = mode_advance(current, nodes, factors, free, dt, p.inductance_h, device.coss_f, resistance_ohm)
        event = None
        # Node voltage is monotone only until i crosses zero. Truncate there
        # FIRST: an endpoint back inside the rails can hide an earlier clamp.
        if current * candidate_i < 0 and abs(current) > 1e-12:
            left, right = 0.0, dt
            for _ in range(36):
                mid = (left + right) / 2
                mi, _, _ = mode_advance(current, nodes, factors, free, mid, p.inductance_h, device.coss_f, resistance_ohm)
                if current * mi > 0:
                    left = mid
                else:
                    right = mid
            dt = right
            candidate_i, candidate_v, _ = mode_advance(current, nodes, factors, free, dt, p.inductance_h, device.coss_f, resistance_ohm)
            event = (dt, "current", -1, 0.0)
        hits = []
        for j in free:
            if candidate_v[j] < low:
                hits.append(("node", j, low))
            elif candidate_v[j] > highs[j]:
                hits.append(("node", j, highs[j]))
        # Resolve diode activation and current reversal before advancing state.
        for kind, j, boundary in hits:
            left, right = 0.0, dt
            start_value = current if kind == "current" else nodes[j] - boundary
            for _ in range(36):
                mid = (left + right) / 2
                mi, mv, _ = mode_advance(current, nodes, factors, free, mid, p.inductance_h, device.coss_f, resistance_ohm)
                value = mi if kind == "current" else mv[j] - boundary
                if start_value * value > 0:
                    left = mid
                else:
                    right = mid
            if event is None or right < event[0]:
                event = (right, kind, j, boundary)
        if event:
            dt = event[0]
        end_i, end_v, charge = mode_advance(current, nodes, factors, free, dt, p.inductance_h, device.coss_f, resistance_ohm)
        integral_i2, peak = mode_current_integrals(current, nodes, factors, free, dt,
                                                  p.inductance_h, device.coss_f, resistance_ohm)
        if event:
            if event[1] == "current":
                end_i = 0.0
            else:
                end_v[event[2]] = event[3]
        source_coeff = 0.0
        bridge_coeffs = [0.0, 0.0]
        for j in range(4):
            coefficient = 0.0
            if j in free:
                coefficient = buses[j] * factors[j] / 2
            elif (j in clamped and nodes[j] > buses[j]) or (j not in switched and window["before"][j]):
                coefficient = buses[j] * factors[j]
            source_coeff += coefficient
            bridge_coeffs[j // 2] += coefficient
        diode_coeff = device.diode_drop_v * sum(abs(factors[j]) for j in clamped)
        supplied, dissipated = source_coeff * charge, diode_coeff * abs(charge)
        source_energy += supplied
        diode_energy += dissipated
        resistor_energy += resistance_ohm * integral_i2
        start_e, end_e = stored(current, nodes), stored(end_i, end_v)
        row = {"t0_s": time, "t1_s": time + dt, "i0_a": current, "i1_a": end_i,
               "free_legs": ":".join(LEGS[j] for j in free),
               "clamped_legs": ":".join(LEGS[j] for j in clamped),
               "inductor_charge_c": charge, "source_energy_j": supplied, "diode_energy_j": dissipated,
               "source1_energy_j": bridge_coeffs[0] * charge, "source2_energy_j": bridge_coeffs[1] * charge,
               "integral_i2_a2_s": integral_i2, "i_peak_a": peak,
               "resistor_energy_j": resistance_ohm * integral_i2,
               "stored_energy0_j": start_e, "stored_energy1_j": end_e,
               "energy_residual_j": supplied - dissipated - resistance_ohm * integral_i2 - (end_e - start_e),
               "cumulative_energy_residual_j": source_energy - diode_energy - resistor_energy - (end_e - initial_energy),
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
                    _, mv, _ = mode_advance(current, nodes, factors, free, mid, p.inductance_h, device.coss_f, resistance_ohm)
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

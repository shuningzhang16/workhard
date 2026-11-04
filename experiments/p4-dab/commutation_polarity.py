"""Necessary current-polarity screen only; no capacitance/dead-time ZVS model."""

from dab_eps import gate_states
from dab_sps import Cycle, Parameters


ZERO_CURRENT_TOL_A = 1e-9  # Numerical zero only, NOT a physical ZVS threshold.


def analyze_edges(cycle: Cycle, alpha_deg: float):
    """One row per leg commutation, including low-side turn-on at high fall.

    iL flows out of primary A, into primary B; n*iL flows into secondary A,
    out of secondary B. Positive node_out_a leaves that switching node.
    During an ideal dead-time onset, Csum*dv_node/dt = -node_out_a.
    Thus -delta_q_high*node_out_a > 0 is the necessary directional check.
    Current comes from the existing ideal periodic waveform at the edge.
    """
    p = cycle.parameters
    legs = [(1, "A", "q1a_high", 1.0), (1, "B", "q1b_high", -1.0),
            (2, "A", "q2a_high", -p.turns_ratio),
            (2, "B", "q2b_high", p.turns_ratio)]
    events = []
    for index, segment in enumerate(cycle.segments):
        previous = cycle.segments[index - 1]
        if abs(previous.i1_a - segment.i0_a) > 1e-9:
            raise ValueError("Expected a continuous periodic waveform")
        before = gate_states((previous.t0_s + previous.t1_s) / 2 * p.frequency_hz,
                             alpha_deg, cycle.phase_deg)
        after = gate_states((segment.t0_s + segment.t1_s) / 2 * p.frequency_hz,
                            alpha_deg, cycle.phase_deg)
        for bridge, leg, key, factor in legs:
            delta = after[key] - before[key]
            if not delta:
                continue
            node_out = factor * segment.i0_a
            directional = -delta * node_out
            status = ("zero_current_boundary" if abs(directional) <= ZERO_CURRENT_TOL_A else
                      "necessary_polarity_met" if directional > 0 else "opposes_transition")
            bus = p.v1_v if bridge == 1 else p.v2_v
            events.append({"t_s": segment.t0_s, "theta_deg": segment.t0_s * p.frequency_hz * 360,
                "bridge": bridge, "leg": leg, "upper_before": before[key], "upper_after": after[key],
                "incoming_device": f"{bridge}{leg}_{'high' if delta > 0 else 'low'}",
                "node_transition": "rising" if delta > 0 else "falling",
                "node_before_v": before[key] * bus, "node_after_v": after[key] * bus,
                "required_iL_sign": "positive" if -delta * factor > 0 else "negative",
                "iL_primary_a": segment.i0_a, "node_out_a": node_out,
                "directional_current_a": directional, "polarity_status": status,
                "zvs_status": "not_evaluated_missing_device_and_deadtime_model"})
    return events


def edge_summary(events):
    result = {"edges": len(events),
              "necessary_met": sum(e["polarity_status"] == "necessary_polarity_met" for e in events),
              "opposed": sum(e["polarity_status"] == "opposes_transition" for e in events),
              "zero_boundary": sum(e["polarity_status"] == "zero_current_boundary" for e in events)}
    for bridge, label in [(1, "primary"), (2, "secondary")]:
        subset = [e for e in events if e["bridge"] == bridge]
        result[f"{label}_necessary_met"] = sum(e["polarity_status"] == "necessary_polarity_met" for e in subset)
        result[f"{label}_min_directional_current_a"] = min(e["directional_current_a"] for e in subset)
    result["interpretation"] = ("has_opposing_edges" if result["opposed"] else
        "has_zero_current_edges" if result["zero_boundary"] else "all_polarities_met_zvs_still_unresolved")
    result["zvs_status"] = "not_evaluated_missing_device_and_deadtime_model"
    return result


def sps_polarity_boundary_deg(parameters: Parameters):
    """Absolute SPS phase needed for all legs' strict polarity, not full ZVS."""
    ratio = parameters.turns_ratio * parameters.v2_v / parameters.v1_v
    return 90 * max(0.0, 1 - 1 / ratio, 1 - ratio)

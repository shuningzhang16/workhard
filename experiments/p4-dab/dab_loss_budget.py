"""Bounded receiver-power matching and first-order MOSFET/gate postprocessing.

The continuous plant is unchanged. Its 0.5 ohm resistance is interpreted here
as an external series resistance, excluding the separately budgeted channels.
Channel and gate estimates are not fed back into the matched plant trajectory.
"""

from dataclasses import dataclass
import math

from dab_continuous import simulate_continuous
from dab_deadtime import LEGS, edge_windows
from dab_eps import simulate_eps


MATCH_TOL_W = 1e-5
MAX_BISECTIONS = 24
LOSS_PARAMETERS = (
    ("typical_25C", 1.8e-3, 41e-9),
    ("listed_max_25C", 2.2e-3, 53e-9),
)
GATE_DRIVE_V = 10.0


@dataclass
class Match:
    status: str
    phase_deg: float | None
    result: object | None
    evaluations: list


def tail_metrics(result, direction):
    tail = result.periods[-10:]
    p1 = math.fsum(r["p1_input_w"] for r in tail) / len(tail)
    p2 = math.fsum(r["p2_output_w"] for r in tail) / len(tail)
    current_error = max(abs(r["periodic_current_difference_a"]) for r in tail)
    power_change = max(abs(a["p2_output_w"]-b["p2_output_w"]) for a, b in zip(tail, tail[1:]))
    return {"p1_input_w": p1, "p2_output_w": p2,
            "received_power_w": p2 if direction == 1 else -p1,
            "input_power_w": p1 if direction == 1 else -p2,
            "receiver": "side_2" if direction == 1 else "side_1",
            "periodic_current_error_a": current_error,
            "period_power_change_w": power_change,
            "period_converged": int(current_error < 1e-8 and power_change < 1e-6)}


def match_actual_power(parameters, alpha_deg, target_w, deadtime_s, phase_bounds, *, direction=1, on_evaluation=None):
    """Match positive receiver power: P2 forward, -P1 in reverse.

    No global reachability or monotonicity claim outside that interval. Each
    trial is a fresh 100-period run, and every trial's finite convergence is
    checked. Failed bracketing is reported without changing the target/deadtime.
    """
    if direction not in (-1, 1) or not math.isfinite(target_w) or target_w <= 0:
        raise ValueError("Require direction +/-1 and a positive finite receiver target")
    evaluations = []
    def evaluate(phase, kind):
        result = simulate_continuous(parameters, alpha_deg, phase, deadtime_s=deadtime_s)
        measured = tail_metrics(result, direction)
        record = {"evaluation_index": len(evaluations), "kind": kind, "phase_deg": phase,
                  "target_received_w": target_w, "direction": direction, **measured,
                  "power_error_w": measured["received_power_w"]-target_w,
                  "search_coordinate_w": direction*measured["received_power_w"]}
        evaluations.append(record)
        if on_evaluation is not None:
            on_evaluation(record)
        return result, record

    low, high = phase_bounds
    low_result, low_row = evaluate(low, "lower_endpoint")
    high_result, high_row = evaluate(high, "upper_endpoint")
    if not low_row["period_converged"] or not high_row["period_converged"]:
        return Match("period_not_converged", None, None, evaluations)
    if low_row["search_coordinate_w"] > high_row["search_coordinate_w"]:
        return Match("interval_not_ascending", None, None, evaluations)
    if not low_row["search_coordinate_w"]-MATCH_TOL_W <= direction*target_w <= high_row["search_coordinate_w"]+MATCH_TOL_W:
        return Match("no_match_in_selected_interval", None, None, evaluations)
    for result, row in ((low_result, low_row), (high_result, high_row)):
        if abs(row["power_error_w"]) <= MATCH_TOL_W:
            return Match("matched", row["phase_deg"], result, evaluations)
    for _ in range(MAX_BISECTIONS):
        phase = (low + high) / 2
        result, row = evaluate(phase, "bisection")
        if not row["period_converged"]:
            return Match("period_not_converged", None, None, evaluations)
        if abs(row["power_error_w"]) <= MATCH_TOL_W:
            return Match("matched", phase, result, evaluations)
        if direction*row["power_error_w"] < 0:
            low = phase
        else:
            high = phase
    return Match("matching_tolerance_not_reached", None, None, evaluations)


def loss_budget(result, parameters, alpha_deg, phase_deg, *, tail_periods=10):
    """Use actual channel on-time and count each physical loss exactly once."""
    first_period = len(result.periods) - tail_periods
    rows = [r for r in result.rows if r["period_index"] >= first_period]
    events = [e for e in result.turnons if e["period_index"] >= first_period]
    duration = tail_periods / parameters.frequency_hz
    schedule = edge_windows(simulate_eps(parameters, alpha_deg, phase_deg), alpha_deg)
    buses = (parameters.v1_v, parameters.v1_v, parameters.v2_v, parameters.v2_v)
    factors = (1.0, -1.0, -parameters.turns_ratio, parameters.turns_ratio)
    channels = {f"{leg}_{side}": {"current_square_integral_a2_s": 0.0, "on_time_s": 0.0, "turnons": 0}
                for leg in LEGS for side in ("high", "low")}
    for row in rows:
        if row["kind"] == "turnon_charge":
            continue
        off = schedule[row["edge_index"]]["switched"] if row["kind"] == "deadtime_RLC" else ()
        for j, leg in enumerate(LEGS):
            if j in off:
                continue  # Neither channel conducts in this leg's dead time.
            side = "high" if row[f"v0_{leg}_v"] > buses[j]/2 else "low"
            entry = channels[f"{leg}_{side}"]
            entry["current_square_integral_a2_s"] += factors[j]**2 * row["integral_i2_a2_s"]
            entry["on_time_s"] += row["t1_s"]-row["t0_s"]
    for event in events:
        channels[f"{event['leg']}_{event['incoming']}"]["turnons"] += 1
    intrinsic = {"external_series_r_w": math.fsum(r["resistor_energy_j"] for r in rows)/duration,
                 "deadtime_diode_w": math.fsum(r["diode_energy_j"] for r in rows)/duration,
                 "turnon_charge_redistribution_w": math.fsum(r["turnon_redistribution_energy_j"] for r in rows)/duration}
    device_rows, totals = [], []
    for label, rds, qg in LOSS_PARAMETERS:
        case_devices = []
        for device, values in channels.items():
            record = {"parameter_case": label, "device": device, **values, "window_duration_s": duration,
                "channel_conduction_w": rds * values["current_square_integral_a2_s"] / duration,
                "gate_charge_w": qg * GATE_DRIVE_V * values["turnons"] / duration}
            device_rows.append(record)
            case_devices.append(record)
        channel = math.fsum(d["channel_conduction_w"] for d in case_devices)
        gate = math.fsum(d["gate_charge_w"] for d in case_devices)
        model_loss = math.fsum(intrinsic.values())
        totals.append({"parameter_case": label, "rds_on_ohm": rds, "qg_c": qg,
            "gate_drive_v": GATE_DRIVE_V, **intrinsic,
            "channel_conduction_postprocess_w": channel, "gate_charge_postprocess_w": gate,
            "plant_model_loss_w": model_loss, "added_postprocess_loss_w": channel+gate,
            "partial_loss_budget_w": model_loss+channel+gate,
            "excluded_residual_coss_diagnostic_w": math.fsum(e["residual_coss_energy_j"] for e in events)/duration,
            "interpretation": "partial first-order estimate; channel/gate not fed back; not measured efficiency"})
    return totals, device_rows

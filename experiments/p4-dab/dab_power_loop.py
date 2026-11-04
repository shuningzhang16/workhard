"""Discrete fixed-bus power PI using only completed-period RL power feedback."""

from dataclasses import dataclass
import math

from dab_transient import Settings, simulate_transient


@dataclass
class Gains:
    kp_deg_per_w: float = 0.4
    ki_deg_per_w_s: float = 2000.0


class PowerPI:
    def __init__(self, references_w: list[float], settings: Settings, gains: Gains):
        self.references = references_w
        self.settings = settings
        self.gains = gains
        self.integral_deg = 0.0
        self.records = []

    def __call__(self, index, completed, previous_phase, latched):
        reference = self.references[index]
        feedback = 0.0 if completed is None else completed["p2_w"]
        feedback_period = -1 if completed is None else completed["period_index"]
        error = reference - feedback
        integral_before = self.integral_deg
        period = 1 / self.settings.circuit.frequency_hz
        integral_proposal = self.gains.ki_deg_per_w_s * period * error
        proportional = self.gains.kp_deg_per_w * error
        limit = self.settings.phase_limit_deg
        slew = self.settings.phase_slew_deg_per_period
        if latched:
            self.integral_deg = 0.0
            # A nonzero power request must remain a nonzero raw phase request,
            # so the existing explicit-clear interlock cannot be bypassed.
            raw = self.gains.kp_deg_per_w * reference
            limited = max(-limit, min(limit, raw))
            predicted = 0.0
            frozen = False
            mode = "latched_integral_reset"
        else:
            raw = proportional + integral_before
            limited = max(-limit, min(limit, raw))
            lower = max(-limit, previous_phase - slew)
            upper = min(limit, previous_phase + slew)
            predicted = max(lower, min(upper, raw))
            frozen = (raw > upper and error > 0) or (raw < lower and error < 0)
            if not frozen:
                self.integral_deg += integral_proposal
            mode = "active"
        self.records.append({"period_index": index, "reference_w": reference,
            "feedback_source_period": feedback_period, "feedback_w": feedback, "control_error_w": error,
            "proportional_deg": proportional, "integral_before_deg": integral_before,
            "integral_proposal_deg": integral_proposal, "integral_after_deg": self.integral_deg,
            "integral_change_deg": self.integral_deg - integral_before,
            "integral_frozen": int(frozen), "raw_phase_request_deg": raw,
            "amplitude_limited_request_deg": limited,
            "amplitude_limited": int(raw != limited),
            "rate_limited": int(not latched and predicted != limited),
            "previous_phase_deg": previous_phase, "predicted_phase_deg": predicted,
            "latched_before_update": int(latched), "controller_mode": mode})
        return raw


def simulate_power_loop(references_w, *, settings=None, gains=None, initial_current_a=0.0,
                        clear_cycles=(), sense_v2=None):
    settings = settings or Settings()
    gains = gains or Gains()
    references = list(references_w)
    if any(not math.isfinite(x) for x in references):
        raise ValueError("Power references must be finite")
    if gains.kp_deg_per_w <= 0 or gains.ki_deg_per_w_s <= 0:
        raise ValueError("Use positive PI gains")
    controller = PowerPI(references, settings, gains)
    # The placeholder request array supplies only the run length. Commands
    # are computed inside the existing continuous-state simulation loop.
    run = simulate_transient(settings, [0.0] * len(references), initial_current_a=initial_current_a,
        clear_cycles=clear_cycles, sense_v2=sense_v2, phase_request=controller)
    for record, actual in zip(controller.records, run.periods):
        # Reporting after the run; these fields are never controller feedback.
        record.update(actual_period_p2_w=actual["p2_w"],
                      actual_tracking_error_w=actual["p2_w"] - record["reference_w"],
                      actual_phase_deg=actual["scheduled_phase_deg"],
                      latched_at_end=actual["latched_at_end"],
                      period_peak_current_a=actual["i_peak_a"])
    return run, controller.records


def scenarios():
    return [
        ("step_and_reverse", [5.0] * 80 + [20.0] * 100 + [-15.0] * 120, {}),
        ("saturation_return", [10.0] * 80 + [100.0] * 100 + [10.0] * 140, {}),
        ("protected_recovery", [100.0] * 30 + [0.0] * 40 + [5.0] * 100,
         {"settings": Settings(overcurrent_a=1.6), "clear_cycles": (20, 50)}),
    ]


def segment_metrics(name, run, control):
    """Observed finite-window performance, with direction-aware overshoot.

    Settling uses max(0.25 W, 2% of target), through the end of this reference
    segment and at least 10 completed periods. No extrapolated settling claim.
    """
    edges = [0] + [k for k in range(1, len(control))
                   if control[k]["reference_w"] != control[k - 1]["reference_w"]] + [len(control)]
    metrics = []
    previous_reference = 0.0
    period = 1 / run.settings.circuit.frequency_hz
    for start, stop in zip(edges, edges[1:]):
        records = control[start:stop]
        target = records[0]["reference_w"]
        direction = 1 if target >= previous_reference else -1
        band = max(0.25, 0.02 * abs(target))
        bad = [j for j, r in enumerate(records) if abs(r["actual_tracking_error_w"]) > band]
        first = bad[-1] + 1 if bad else 0
        settled = len(records) - first >= 10
        metrics.append({"scenario": name, "start_period": start, "stop_period_exclusive": stop,
            "target_w": target, "previous_target_w": previous_reference, "tolerance_band_w": band,
            "settled_in_observed_window": int(settled),
            "settling_completed_periods": first + 1 if settled else "",
            "settling_time_s": (first + 1) * period if settled else "",
            "tail_mean_error_w": math.fsum(r["actual_tracking_error_w"] for r in records[-10:]) / min(10, len(records)),
            "max_absolute_error_w": max(abs(r["actual_tracking_error_w"]) for r in records),
            "directional_overshoot_w": max(0.0, max(direction * r["actual_tracking_error_w"] for r in records)),
            "peak_current_a": max(r["period_peak_current_a"] for r in records),
            "amplitude_limited_updates": sum(r["amplitude_limited"] for r in records),
            "rate_limited_updates": sum(r["rate_limited"] for r in records),
            "integral_frozen_updates": sum(r["integral_frozen"] for r in records),
            "integral_min_deg": min(r["integral_after_deg"] for r in records),
            "integral_max_deg": max(r["integral_after_deg"] for r in records),
            "latched_periods": sum(r["latched_at_end"] for r in records)})
        previous_reference = target
    return metrics

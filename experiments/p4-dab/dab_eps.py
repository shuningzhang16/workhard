"""Primary-bridge EPS: centered zero intervals plus external phase shift."""

import math

from dab_sps import Cycle, Parameters, integrate_intervals, waveform_rows


ALPHA_GRID_DEG = tuple(range(0, 181, 15))
POWER_MATCH_TOL_W = 1e-7


def gate_states(turns: float, alpha_deg: float, phase_deg: float) -> dict[str, int]:
    """Upper switch states; each lower switch is its ideal complement.

    alpha is zero-level width about each original primary transition.
    Primary leg separation = 180-alpha degrees. External phi is referenced
    to the primary pulse center, so alpha=0 exactly recovers SPS timing.
    """
    half_zero = alpha_deg / 720
    delay = phase_deg / 360

    def high(shift):
        return int((turns - shift) % 1 < 0.5)

    q2a = high(delay)
    return {"q1a_high": high(half_zero), "q1b_high": high(0.5 - half_zero),
            "q2a_high": q2a, "q2b_high": 1 - q2a}


def simulate_eps(parameters: Parameters, alpha_deg: float, phase_deg: float) -> Cycle:
    parameters.validate()
    if not math.isfinite(alpha_deg) or not 0 <= alpha_deg <= 180:
        raise ValueError("alpha_deg must be in [0, 180]")
    if not math.isfinite(phase_deg) or abs(phase_deg) > 90:
        raise ValueError("EPS phase_deg must be in [-90, 90]")
    period = 1 / parameters.frequency_hz
    h = alpha_deg / 720
    delay = phase_deg / 360
    edges = sorted({0.0, 1.0, h, 0.5 + h, 0.5 - h, (1 - h) % 1,
                    delay % 1, (delay + 0.5) % 1})
    intervals = []
    for left, right in zip(edges, edges[1:]):
        q = gate_states((left + right) / 2, alpha_deg, phase_deg)
        v1 = parameters.v1_v * (q["q1a_high"] - q["q1b_high"])
        v2 = parameters.turns_ratio * parameters.v2_v * (q["q2a_high"] - q["q2b_high"])
        intervals.append((left * period, right * period, v1, v2))
    return integrate_intervals(parameters, phase_deg, intervals)


def match_power(parameters: Parameters, target_w: float, alpha_deg: float):
    """Return a matching cycle or None, plus |P(phi=90)| for this alpha.

    The centered waveform has nondecreasing P on phi in [0,90]. Search
    only this branch. Forty bisections bound work; no optimization framework.
    """
    if not math.isfinite(target_w):
        raise ValueError("target_w must be finite")
    maximum = simulate_eps(parameters, alpha_deg, 90).metrics["p2_time_w"]
    if abs(target_w) > maximum + POWER_MATCH_TOL_W:
        return None, maximum
    low, high = 0.0, 90.0
    sign = -1 if target_w < 0 else 1
    for _ in range(40):
        midpoint = (low + high) / 2
        cycle = simulate_eps(parameters, alpha_deg, sign * midpoint)
        if sign * cycle.metrics["p2_time_w"] < abs(target_w):
            low = midpoint
        else:
            high = midpoint
    cycle = simulate_eps(parameters, alpha_deg, sign * (low + high) / 2)
    if abs(cycle.metrics["p2_time_w"] - target_w) > POWER_MATCH_TOL_W:
        return None, maximum
    return cycle, maximum


def search_eps(parameters: Parameters, target_w: float):
    """Minimize RMS among 13 matched alpha candidates; not a global optimum."""
    candidates = []
    best = None
    best_key = None
    for alpha in ALPHA_GRID_DEG:
        cycle, maximum = match_power(parameters, target_w, alpha)
        row = {"alpha_deg": alpha, "internal_leg_shift_deg": 180 - alpha,
               "target_w": target_w, "max_abs_power_in_branch_w": maximum,
               "status": "matched" if cycle else "no_match_in_branch",
               "phase_deg": "", "p2_time_w": "", "power_match_error_w": "",
               "i_peak_a": "", "i_rms_a": "", "power_balance_w": "",
               "i_mean_a": "", "periodic_error_a": ""}
        if cycle:
            m = cycle.metrics
            row.update(phase_deg=cycle.phase_deg, p2_time_w=m["p2_time_w"],
                       power_match_error_w=m["p2_time_w"] - target_w,
                       **{key: m[key] for key in ["i_peak_a", "i_rms_a", "power_balance_w",
                                                  "i_mean_a", "periodic_error_a"]})
            key = (m["i_rms_a"], m["i_peak_a"], alpha)
            if best_key is None or key < best_key:
                best, best_key = (alpha, cycle), key
        candidates.append(row)
    return best, candidates


def timing_rows(cycle: Cycle, alpha_deg: float):
    """Two periods, one CSV row per exact switching interval with gate states."""
    for row in waveform_rows(cycle, periods=2, samples_per_period=1):
        turns = (row["t0_s"] + row["t1_s"]) / 2 * cycle.parameters.frequency_hz
        yield {**row, **gate_states(turns, alpha_deg, cycle.phase_deg)}

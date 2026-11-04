"""State-preserving SPS RL transient and sampled protection teaching model."""

from dataclasses import dataclass, field
import math
from typing import Callable

from dab_sps import Parameters


@dataclass
class Settings:
    circuit: Parameters = field(default_factory=Parameters)
    series_resistance_ohm: float = 0.5
    phase_limit_deg: float = 60.0
    phase_slew_deg_per_period: float = 6.0
    samples_per_period: int = 20
    overcurrent_a: float = 8.0
    clear_current_a: float = 0.2
    sensed_v2_limit_v: float = 15.0


@dataclass
class Run:
    settings: Settings
    rows: list[dict]
    periods: list[dict]
    samples: list[dict]
    events: list[dict]


def rl_step(i0: float, voltage: float, dt: float, inductance: float, resistance: float):
    """Exact RL endpoint, integral(i dt), integral(i^2 dt) for constant voltage.

    Integrals are evaluated independently of the energy-balance residual.
    Positive R is required; this step never centers or resets current.
    """
    tau = inductance / resistance
    steady = voltage / resistance
    offset = i0 - steady
    z1 = -math.expm1(-dt / tau)
    z2 = -math.expm1(-2 * dt / tau)
    i1 = i0 - offset * z1
    integral_i = steady * dt + offset * tau * z1
    integral_i2 = steady**2 * dt + 2 * steady * offset * tau * z1 + offset**2 * tau * z2 / 2
    return i1, integral_i, integral_i2


def simulate_transient(settings: Settings, requests: list[float], *, initial_current_a=0.0,
                       clear_cycles=(), sense_v2: Callable[[float], float] | None = None) -> Run:
    """Carry the actual current across all intervals and command boundaries.

    Inputs update at the start of each switching period. Protection samples
    every T/N; trips force both ideal bridges to zero immediately at the sample.
    Clear requests are explicit period indices and require zero command,
    no active sampled fault, and |i| <= clear_current_a. No automatic restart.
    sense_v2 receives elapsed time in switching periods; it is a detector input
    only, never an output capacitor state or a change to the physical V2 source.
    """
    p = settings.circuit
    p.validate()
    positive = [settings.series_resistance_ohm, settings.phase_limit_deg,
                settings.phase_slew_deg_per_period, settings.overcurrent_a,
                settings.clear_current_a, settings.sensed_v2_limit_v]
    if any(not math.isfinite(x) or x <= 0 for x in positive):
        raise ValueError("Transient settings must be finite and positive")
    if not isinstance(settings.samples_per_period, int) or settings.samples_per_period < 1:
        raise ValueError("samples_per_period must be a positive integer")
    if settings.phase_limit_deg > 90 or settings.clear_current_a >= settings.overcurrent_a:
        raise ValueError("Require phase limit <=90 and clear current below overcurrent threshold")
    if not math.isfinite(initial_current_a) or any(not math.isfinite(x) for x in requests):
        raise ValueError("Current and requests must be finite")
    sense_v2 = sense_v2 or (lambda turns: p.v2_v)
    period = 1 / p.frequency_hz
    resistance = settings.series_resistance_ohm
    current = initial_current_a
    phase = 0.0
    latched = False
    reason = ""
    rows, samples, events, periods = [], [], [], []
    total_e1 = total_e2 = total_er = 0.0
    initial_energy = 0.5 * p.inductance_h * current**2
    sample_edges = {round(j / settings.samples_per_period, 14)
                    for j in range(settings.samples_per_period)}
    sensed = p.v2_v

    def sample(turns, request, clear):
        nonlocal latched, reason, phase, sensed
        sensed = sense_v2(turns)
        if not math.isfinite(sensed):
            raise ValueError("Bus sense input must be finite")
        fault = "overcurrent" if abs(current) > settings.overcurrent_a else (
            "bus_overvoltage_input" if sensed > settings.sensed_v2_limit_v else "")
        if fault and not latched:
            latched, reason, phase = True, fault, 0.0
            events.append({"t_s": turns * period, "event": "trip", "reason": reason,
                           "i_a": current, "sensed_v2_v": sensed, "request_deg": request})
        if clear and latched:
            accepted = not fault and request == 0 and abs(current) <= settings.clear_current_a
            events.append({"t_s": turns * period, "event": "clear_accepted" if accepted else "clear_denied",
                           "reason": reason, "i_a": current, "sensed_v2_v": sensed,
                           "request_deg": request})
            if accepted:
                latched, reason, phase = False, "", 0.0
        samples.append({"t_s": turns * period, "i_a": current, "sensed_v2_v": sensed,
                        "active_fault": fault, "latched": int(latched), "latched_reason": reason,
                        "clear_requested": int(clear), "request_deg": request})

    for k, request in enumerate(requests):
        start_current = current
        sample(k, request, k in clear_cycles)
        target = max(-settings.phase_limit_deg, min(settings.phase_limit_deg, request))
        if latched:
            phase = 0.0
        else:
            change = max(-settings.phase_slew_deg_per_period,
                         min(settings.phase_slew_deg_per_period, target - phase))
            phase += change
        scheduled_phase = phase
        delay = scheduled_phase / 360
        # Coalesce coincident switching/sample edges at 1e-14 of a period.
        edges = sorted(sample_edges | {1.0, 0.5, round(delay % 1, 14),
                                      round((delay + 0.5) % 1, 14)})
        period_rows = []
        for left, right in zip(edges, edges[1:]):
            is_sample = left in sample_edges
            if is_sample and left != 0:
                sample(k + left, request, False)
            midpoint = (left + right) / 2
            v1 = 0.0 if latched else p.v1_v * (1 if midpoint < 0.5 else -1)
            v2 = 0.0 if latched else p.turns_ratio * p.v2_v * (
                1 if (midpoint - delay) % 1 < 0.5 else -1)
            t0, t1 = (k + left) * period, (k + right) * period
            dt = t1 - t0
            i0 = current
            current, integral_i, integral_i2 = rl_step(i0, v1 - v2, dt, p.inductance_h, resistance)
            e1, e2, er = v1 * integral_i, v2 * integral_i, resistance * integral_i2
            energy0, energy1 = 0.5 * p.inductance_h * i0**2, 0.5 * p.inductance_h * current**2
            residual = e1 - e2 - er - (energy1 - energy0)
            total_e1 += e1
            total_e2 += e2
            total_er += er
            row = {"period_index": k, "t0_s": t0, "t1_s": t1, "request_deg": request,
                   "limited_target_deg": target, "scheduled_phase_deg": scheduled_phase,
                   "sample_at_t0": int(is_sample), "latched": int(latched), "reason": reason,
                   "v1_v": v1, "v2_prime_v": v2, "sensed_v2_v": sensed,
                   "i0_a": i0, "i1_a": current, "integral_i_a_s": integral_i,
                   "integral_i2_a2_s": integral_i2, "e1_j": e1, "e2_j": e2, "er_j": er,
                   "inductor_e0_j": energy0, "inductor_e1_j": energy1,
                   "energy_residual_j": residual,
                   "cumulative_energy_residual_j": total_e1 - total_e2 - total_er - (energy1 - initial_energy)}
            rows.append(row)
            period_rows.append(row)
        periods.append({"period_index": k, "t0_s": k * period, "request_deg": request,
                        "limited_target_deg": target, "scheduled_phase_deg": scheduled_phase,
                        "latched_at_end": int(latched), "i_start_a": start_current, "i_end_a": current,
                        "p1_w": math.fsum(r["e1_j"] for r in period_rows) / period,
                        "p2_w": math.fsum(r["e2_j"] for r in period_rows) / period,
                        "resistor_power_w": math.fsum(r["er_j"] for r in period_rows) / period,
                        "i_mean_a": math.fsum(r["integral_i_a_s"] for r in period_rows) / period,
                        "i_rms_a": math.sqrt(math.fsum(r["integral_i2_a2_s"] for r in period_rows) / period),
                        "i_peak_a": max(abs(r[key]) for r in period_rows for key in ["i0_a", "i1_a"])})
    return Run(settings, rows, periods, samples, events)


def teaching_scenarios():
    """Small fixed experiment matrix; no hardware communication."""
    return [
        ("constant_forward", Settings(), [30.0] * 120,
         {"initial_current_a": 0.37}),
        ("direction_reversal", Settings(), [30.0] * 60 + [-30.0] * 100, {}),
        ("overcurrent_recovery", Settings(overcurrent_a=1.6),
         [120.0] * 20 + [0.0] * 30 + [-min(2.0 * (j + 1), 30.0) for j in range(50)],
         {"clear_cycles": (10, 40)}),
        ("bus_input_recovery", Settings(), [30.0] * 20 + [0.0] * 30 + [-30.0] * 30,
         {"clear_cycles": (22, 40), "sense_v2": lambda turns: 17.0 if 20.33 <= turns < 25 else 12.0}),
    ]


def run_teaching_scenarios():
    return {name: simulate_transient(settings, requests, **options)
            for name, settings, requests, options in teaching_scenarios()}

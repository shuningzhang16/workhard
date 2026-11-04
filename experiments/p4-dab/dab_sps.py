"""Ideal DAB SPS periodic model; SI units; standard library only."""

from dataclasses import dataclass
import math


@dataclass
class Parameters:
    v1_v: float = 24.0
    v2_v: float = 12.0
    turns_ratio: float = 2.0  # n = N1/N2
    frequency_hz: float = 20_000.0
    inductance_h: float = 100e-6  # Total series inductance referred to side 1.

    def validate(self):
        for name, value in vars(self).items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")


@dataclass
class Segment:
    t0_s: float
    t1_s: float
    v1_v: float
    v2_prime_v: float
    i0_a: float
    i1_a: float


@dataclass
class Cycle:
    parameters: Parameters
    phase_deg: float
    segments: list[Segment]
    metrics: dict[str, float]


def analytical_power(parameters: Parameters, phase_deg: float) -> float:
    """Positive phase means side 2 lags side 1; positive P goes 1 -> 2."""
    phi = math.radians(phase_deg)
    omega = 2 * math.pi * parameters.frequency_hz
    return (
        parameters.v1_v * parameters.turns_ratio * parameters.v2_v
        / (omega * parameters.inductance_h)
        * phi * (1 - abs(phi) / math.pi)
    )


def simulate(parameters: Parameters, phase_deg: float) -> Cycle:
    """Integrate di/dt=(v1-v2')/L over switching events, then select zero DC.

    The ideal lossless inductor does not settle by itself. Subtracting the
    time-weighted mean selects the zero-DC periodic orbit, not a startup run.
    Current construction never uses the analytical power expression.
    """
    parameters.validate()
    if not math.isfinite(phase_deg) or abs(phase_deg) > 180:
        raise ValueError("phase_deg must be finite and in [-180, 180]")
    period = 1 / parameters.frequency_hz
    delay = phase_deg / 360.0
    edges = sorted({0.0, 0.5, 1.0, delay % 1.0, (delay + 0.5) % 1.0})
    provisional = []
    current = 0.0
    for left, right in zip(edges, edges[1:]):
        midpoint = (left + right) / 2
        v1 = parameters.v1_v * (1 if midpoint < 0.5 else -1)
        v2 = parameters.turns_ratio * parameters.v2_v * (
            1 if (midpoint - delay) % 1 < 0.5 else -1
        )
        dt = (right - left) * period
        next_current = current + (v1 - v2) / parameters.inductance_h * dt
        provisional.append(Segment(left * period, right * period,
                                   v1, v2, current, next_current))
        current = next_current

    dc_offset = math.fsum(
        (s.i0_a + s.i1_a) / 2 * (s.t1_s - s.t0_s) for s in provisional
    ) / period
    segments = [Segment(s.t0_s, s.t1_s, s.v1_v, s.v2_prime_v,
                        s.i0_a - dc_offset, s.i1_a - dc_offset)
                for s in provisional]
    mean_current = math.fsum(
        (s.i0_a + s.i1_a) / 2 * (s.t1_s - s.t0_s) for s in segments
    ) / period
    p1 = math.fsum(
        s.v1_v * (s.i0_a + s.i1_a) / 2 * (s.t1_s - s.t0_s)
        for s in segments
    ) / period
    p2 = math.fsum(
        s.v2_prime_v * (s.i0_a + s.i1_a) / 2 * (s.t1_s - s.t0_s)
        for s in segments
    ) / period
    rms_squared = math.fsum(
        (s.i0_a**2 + s.i0_a * s.i1_a + s.i1_a**2) / 3
        * (s.t1_s - s.t0_s) for s in segments
    ) / period
    expected = analytical_power(parameters, phase_deg)
    metrics = {
        "p_analytic_w": expected,
        "p1_time_w": p1,
        "p2_time_w": p2,
        "power_error_w": p2 - expected,
        "power_balance_w": p1 - p2,
        "i_peak_a": max(abs(i) for s in segments for i in (s.i0_a, s.i1_a)),
        "i_rms_a": math.sqrt(rms_squared),
        "i_mean_a": mean_current,
        "periodic_error_a": segments[-1].i1_a - segments[0].i0_a,
    }
    return Cycle(parameters, phase_deg, segments, metrics)


def waveform_rows(cycle: Cycle, periods: int = 2, samples_per_period: int = 200):
    """Interval data includes every switching edge; no interpolation across it.

    Voltages are constant on [t0,t1); currents are values at both endpoints.
    p1_avg and p2_avg are interval means, not instantaneous measurements.
    Extra subdivisions only sample the already solved linear trajectory.
    """
    period = 1 / cycle.parameters.frequency_hz
    for k in range(periods):
        for s in cycle.segments:
            count = max(1, math.ceil((s.t1_s - s.t0_s) / period * samples_per_period))
            for j in range(count):
                t0 = s.t0_s + (s.t1_s - s.t0_s) * j / count
                t1 = s.t0_s + (s.t1_s - s.t0_s) * (j + 1) / count
                i0 = s.i0_a + (s.i1_a - s.i0_a) * j / count
                i1 = s.i0_a + (s.i1_a - s.i0_a) * (j + 1) / count
                yield {
                    "period_index": k,
                    "t0_s": t0 + k * period,
                    "t1_s": t1 + k * period,
                    "v1_v": s.v1_v,
                    "v2_prime_v": s.v2_prime_v,
                    "vL_v": s.v1_v - s.v2_prime_v,
                    "iL0_a": i0,
                    "iL1_a": i1,
                    "p1_avg_w": s.v1_v * (i0 + i1) / 2,
                    "p2_avg_w": s.v2_prime_v * (i0 + i1) / 2,
                }

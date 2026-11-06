"""Independent ideal-SPS R-L reference values, not PLECS simulation output.

No PLECS process, results, files, or RPC is read. Integrate exact constant-voltage
intervals and report the final period of a 120-period zero-current startup.
"""
import json
import math


def reference(phase_deg):
    period, voltage, inductance, resistance = 50e-6, 24.0, 100e-6, 0.5
    tau, delay = inductance / resistance, phase_deg / 360
    edges = sorted({0.0, 0.5, 1.0, delay % 1, (delay + 0.5) % 1})
    current = 0.0
    for _ in range(120):
        charge_sum = i2_sum = e1 = e2 = 0.0
        peak = abs(current)
        start = current
        for left, right in zip(edges, edges[1:]):
            midpoint, dt = (left + right) / 2, (right - left) * period
            v1 = voltage * (1 if midpoint < 0.5 else -1)
            v2 = voltage * (1 if (midpoint - delay) % 1 < 0.5 else -1)
            equilibrium = (v1 - v2) / resistance
            transient = current - equilibrium
            decay = math.exp(-dt / tau)
            charge = equilibrium * dt + transient * tau * (1 - decay)
            i2 = (equilibrium**2 * dt + 2 * equilibrium * transient * tau * (1 - decay)
                  + transient**2 * tau / 2 * (1 - decay**2))
            current = equilibrium + transient * decay
            charge_sum += charge
            i2_sum += i2
            e1 += v1 * charge
            e2 += v2 * charge
            peak = max(peak, abs(current))
        delta_energy = inductance * (current**2 - start**2) / 2
    return {'source': 'independent analytic R-L calculation; NOT PLECS output',
            'phase_deg': phase_deg, 'periods': 120,
            'p1_w': e1 / period, 'p2_w': e2 / period,
            'r_loss_w': resistance * i2_sum / period,
            'i_rms_a': math.sqrt(i2_sum / period), 'i_peak_a': peak,
            'i_start_a': start, 'i_end_a': current,
            'energy_residual_j': e1 - e2 - resistance * i2_sum - delta_energy}


if __name__ == '__main__':
    print(json.dumps([reference(30), reference(-30)], indent=2))

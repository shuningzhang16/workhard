"""Sampled PI/protection on the persistent RLC/Coss SPS bridge state.

The update origin is primary carrier phase 90 degrees. With phase limited to
60 degrees, both secondary edges stay inside the same update period. Pending
turn-ons and capacitor states belong to the plant, never to a periodic template.
"""

from dataclasses import dataclass
import math

from dab_power_loop import Gains, PowerPI
from dab_switching import BridgeState
from dab_transient import Settings


@dataclass
class ControlledRun:
    settings: Settings
    rows: list
    periods: list
    samples: list
    events: list
    turnons: list
    gate_events: list


def simulate_switching_control(settings, requests, *, phase_request=None, deadtime_s=150e-9,
                              initial_current_a=0.0, clear_cycles=(), sense_v2=None,
                              deadtime_step_s=None):
    p = settings.circuit
    p.validate()
    positive = (settings.series_resistance_ohm, settings.phase_limit_deg,
        settings.phase_slew_deg_per_period, settings.overcurrent_a, settings.clear_current_a,
        settings.sensed_v2_limit_v)
    if any(not math.isfinite(x) or x <= 0 for x in positive):
        raise ValueError("Settings must be finite and positive")
    if not 0 < settings.phase_limit_deg <= 60 or settings.clear_current_a >= settings.overcurrent_a:
        raise ValueError("Use phase limit <=60 degrees and clear current below trip threshold")
    if not isinstance(settings.samples_per_period, int) or settings.samples_per_period < 1:
        raise ValueError("Require a positive integer sample count")
    if not requests or any(not math.isfinite(x) for x in requests) or not math.isfinite(initial_current_a):
        raise ValueError("Require nonempty finite requests and finite initial current")
    period = 1/p.frequency_hz
    if not 0 < deadtime_s < period/12:
        raise ValueError("Dead time must fit inside the fixed-reference edge margin")
    sense_v2 = sense_v2 or (lambda turns: p.v2_v)
    bridge = BridgeState(p, [1, 0, 1, 0], initial_current_a=initial_current_a,
                         resistance_ohm=settings.series_resistance_ohm, deadtime_step_s=deadtime_step_s)
    samples, events, periods, gate_events = [], [], [], []
    pending = {}  # leg -> absolute turn-on time in carrier periods
    phase, latched, reason = 0.0, False, ""

    def command(targets, turns, cause):
        changes = {}
        for j, target in targets.items():
            if bridge.gates[j] == target:
                continue
            if bridge.gates[j] is None and bridge.off_info[j]["target"] == target:
                continue  # Keep a previously scheduled safe turn-on.
            due = round(turns+deadtime_s/period, 14)
            gate_events.append({"t_s": bridge.time, "leg_index": j,
                "old_gate": -1 if bridge.gates[j] is None else bridge.gates[j],
                "target_gate": target, "turnon_due_s": due*period,
                "replaced_pending": int(j in pending), "cause": cause,
                "period_index": bridge.period_index})
            pending[j] = due
            changes[j] = target
        bridge.turn_off(changes)

    def sample(turns, request, clear):
        nonlocal latched, reason, phase
        sensed = sense_v2(turns)
        if not math.isfinite(sensed):
            raise ValueError("Bus sense must be finite")
        fault = "overcurrent" if abs(bridge.current) > settings.overcurrent_a else (
            "bus_overvoltage_input" if sensed > settings.sensed_v2_limit_v else "")
        if fault and not latched:
            latched, bridge.latched, reason, phase = True, True, fault, 0.0
            events.append({"t_s": bridge.time, "event": "trip", "reason": reason,
                "i_a": bridge.current, "sensed_v2_v": sensed, "request_deg": request})
            # Both bridge voltages become zero after actual dead-time commutation
            # into their low channels. Neither voltage nor current is reset here.
            command(dict.fromkeys(range(4), 0), turns, "fault_zero_bridge")
        if clear and latched:
            accepted = not fault and request == 0 and abs(bridge.current) <= settings.clear_current_a
            events.append({"t_s": bridge.time, "event": "clear_accepted" if accepted else "clear_denied",
                "reason": reason, "i_a": bridge.current, "sensed_v2_v": sensed, "request_deg": request})
            if accepted:
                latched, bridge.latched, reason, phase = False, False, "", 0.0
                # Restore the carrier's quarter-cycle state by switching, not
                # assigning capacitor voltages. The re-enable transient is logged.
                command({0: 1, 1: 0, 2: 1, 3: 0}, turns, "explicit_reenable")
        samples.append({"t_s": bridge.time, "i_a": bridge.current, "sensed_v2_v": sensed,
            "active_fault": fault, "latched": int(latched), "latched_reason": reason,
            "clear_requested": int(clear), "request_deg": request})

    for k, request in enumerate(requests):
        bridge.period_index = k
        first_row, first_turnon = len(bridge.rows), len(bridge.turnons)
        if phase_request is not None:
            request = phase_request(k, periods[-1] if periods else None, phase, latched)
        if not math.isfinite(request):
            raise ValueError("Controller request must be finite")
        sample(float(k), request, k in clear_cycles)
        target = max(-settings.phase_limit_deg, min(settings.phase_limit_deg, request))
        if not latched:
            phase += max(-settings.phase_slew_deg_per_period,
                         min(settings.phase_slew_deg_per_period, target-phase))
        scheduled_phase = phase
        schedule = {}
        for fraction, targets in ((0.25, {0: 0, 1: 1}), (0.75, {0: 1, 1: 0}),
                (0.25+phase/360, {2: 0, 3: 1}), (0.75+phase/360, {2: 1, 3: 0})):
            schedule.setdefault(round(k+fraction, 14), {}).update(targets)
        sample_times = {round(k+j/settings.samples_per_period, 14)
                        for j in range(1, settings.samples_per_period)}
        end = float(k+1)
        while bridge.time < end*period:
            turns = min([end, *schedule, *sample_times, *pending.values()])
            bridge.advance(turns*period)
            if turns in sample_times:
                sample(turns, request, False)  # Protection has priority at a tie.
                sample_times.remove(turns)
            if turns in schedule:
                targets = schedule.pop(turns)
                if not latched:
                    command(targets, turns, "carrier_edge")
            due = {j: bridge.off_info[j]["target"] for j, time in pending.items() if time == turns}
            if due:
                bridge.turn_on(due)
                for j in due:
                    del pending[j]
        summary = bridge.summarize(first_row, first_turnon)
        summary.update(t0_s=k*period, request_deg=request, limited_target_deg=target,
            scheduled_phase_deg=scheduled_phase, latched_at_end=int(latched),
            p1_w=summary["p1_input_w"], p2_w=summary["p2_output_w"])
        periods.append(summary)
    return ControlledRun(settings, bridge.rows, periods, samples, events, bridge.turnons, gate_events)


def simulate_continuous_loop(references_w, *, settings=None, gains=None, **options):
    settings, gains = settings or Settings(), gains or Gains()
    references = list(references_w)
    if any(not math.isfinite(x) for x in references) or gains.kp_deg_per_w <= 0 or gains.ki_deg_per_w_s <= 0:
        raise ValueError("Require finite references and positive PI gains")
    controller = PowerPI(references, settings, gains)
    run = simulate_switching_control(settings, [0.0]*len(references), phase_request=controller, **options)
    for record, actual in zip(controller.records, run.periods):
        record.update(actual_period_p2_w=actual["p2_w"],
            actual_tracking_error_w=actual["p2_w"]-record["reference_w"],
            actual_phase_deg=actual["scheduled_phase_deg"], latched_at_end=actual["latched_at_end"],
            period_peak_current_a=actual["i_peak_a"])
    return run, controller.records

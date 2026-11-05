"""Persistent bridge state between arbitrary gate, sample and period events.

No carrier timing lives in this class. Off legs retain their capacitor voltages;
held legs retain their channel states. All RLC evolution uses simulate_window.
"""

import math

from dab_deadtime import Device, LEGS, simulate_window
from dab_transient import rl_step


class BridgeState:
    def __init__(self, parameters, gates, *, initial_current_a=0.0, resistance_ohm=0.5,
                 device=None, deadtime_step_s=None):
        self.p, self.device, self.resistance = parameters, device or Device(), resistance_ohm
        self.buses = (parameters.v1_v, parameters.v1_v, parameters.v2_v, parameters.v2_v)
        self.gates = list(gates)
        self.nodes = [q*b for q, b in zip(gates, self.buses)]  # Once, at initialization.
        self.current, self.time = initial_current_a, 0.0
        self.rows, self.turnons = [], []
        self.off_info = {}
        self.source_sum = self.loss_sum = 0.0
        self.initial_energy = self.stored(self.current, self.nodes)
        self.deadtime_step_s = deadtime_step_s
        self.period_index = 0
        self.latched = False

    def stored(self, current, nodes):
        return 0.5*self.p.inductance_h*current**2 + math.fsum(
            0.5*self.device.coss_f*(v*v+(bus-v)**2) for v, bus in zip(nodes, self.buses))

    def append(self, kind, stop, end_i, end_nodes, e1, e2, er, ed, eon, charge, i2, peak):
        before, after = self.stored(self.current, self.nodes), self.stored(end_i, end_nodes)
        self.source_sum += e1+e2
        self.loss_sum += er+ed+eon
        row = {"period_index": self.period_index, "kind": kind, "edge_index": -1,
            "t0_s": self.time, "t1_s": stop, "i0_a": self.current, "i1_a": end_i,
            "source1_energy_j": e1, "source2_energy_j": e2, "resistor_energy_j": er,
            "diode_energy_j": ed, "turnon_redistribution_energy_j": eon,
            "inductor_charge_c": charge, "integral_i2_a2_s": i2, "i_peak_a": peak,
            "stored_energy0_j": before, "stored_energy1_j": after,
            "energy_residual_j": e1+e2-er-ed-eon-(after-before),
            "cumulative_energy_residual_j": self.source_sum-self.loss_sum-(after-self.initial_energy),
            "latched": int(self.latched)}
        for j, leg in enumerate(LEGS):
            row[f"v0_{leg}_v"], row[f"v1_{leg}_v"] = self.nodes[j], end_nodes[j]
            row[f"gate_{leg}"] = -1 if self.gates[j] is None else self.gates[j]
        self.rows.append(row)
        self.current, self.nodes, self.time = end_i, list(end_nodes), stop

    def advance(self, stop):
        if stop <= self.time:
            return
        off = [j for j, gate in enumerate(self.gates) if gate is None]
        if not off:
            v1 = self.nodes[0]-self.nodes[1]
            v2 = self.p.turns_ratio*(self.nodes[2]-self.nodes[3])
            end_i, charge, i2 = rl_step(self.current, v1-v2, stop-self.time,
                                      self.p.inductance_h, self.resistance)
            self.append("active_RL", stop, end_i, self.nodes, v1*charge, -v2*charge,
                        self.resistance*i2, 0.0, 0.0, charge, i2, max(abs(self.current), abs(end_i)))
            return
        start = self.time
        before = [self.off_info[j]["old_gate"] if j in off else g for j, g in enumerate(self.gates)]
        after = [self.off_info[j]["target"] if j in off else g for j, g in enumerate(self.gates)]
        window = {"parameters": self.p, "before": before, "after": after, "switched": off,
                  "initial_current_a": self.current, "initial_nodes_v": self.nodes,
                  "next_edge_gap_s": math.inf}
        local, _ = simulate_window(window, stop-start, device=self.device,
            resistance_ohm=self.resistance, sample_step_s=self.deadtime_step_s or stop-start)
        for index, r in enumerate(local):
            self.append("deadtime_RLC", stop if index == len(local)-1 else start+r["t1_s"],
                r["i1_a"], [r[f"v1_{leg}_v"] for leg in LEGS], r["source1_energy_j"],
                r["source2_energy_j"], r["resistor_energy_j"], r["diode_energy_j"], 0.0,
                r["inductor_charge_c"], r["integral_i2_a2_s"], r["i_peak_a"])

    def turn_off(self, targets):
        for j, target in targets.items():
            if self.gates[j] is not None:
                self.off_info[j] = {"old_gate": self.gates[j], "off_time_s": self.time,
                                    "off_current_a": self.current, "target": target}
            else:
                self.off_info[j]["target"] = target
            self.gates[j] = None

    def turn_on(self, targets):
        end_nodes, source_jump, loss = list(self.nodes), [0.0, 0.0], 0.0
        for j, target_gate in targets.items():
            if self.gates[j] is not None:
                raise AssertionError("A channel must turn off before the next turn-on")
            target = target_gate*self.buses[j]
            dv = target-self.nodes[j]
            supplied = self.device.coss_f*self.buses[j]*dv*(1 if target_gate else -1)
            dissipated = self.device.coss_f*dv**2
            source_jump[j//2] += supplied
            loss += dissipated
            vds = self.buses[j]-self.nodes[j] if target_gate else self.nodes[j]
            info = self.off_info[j]
            self.turnons.append({"period_index": self.period_index, "t_s": self.time, "leg": LEGS[j],
                "incoming": "high" if target_gate else "low", "off_time_s": info["off_time_s"],
                "actual_off_duration_s": self.time-info["off_time_s"],
                "iL_initial_a": info["off_current_a"], "iL_turnon_a": self.current,
                "i_after_turnon_a": self.current, "node_at_turnon_v": self.nodes[j],
                "node_after_turnon_v": target, "incoming_vds_at_turnon_v": vds,
                "zvs_in_this_model": int(vds <= 1e-6),
                "residual_coss_energy_j": 0.5*self.device.coss_f*max(vds, 0)**2,
                "source_jump_energy_j": supplied, "turnon_redistribution_energy_j": dissipated,
                "latched": int(self.latched)})
            end_nodes[j] = target
        self.append("turnon_charge", self.time, self.current, end_nodes, *source_jump,
                    0.0, 0.0, loss, 0.0, 0.0, abs(self.current))
        for j, target in targets.items():
            self.gates[j] = target
            del self.off_info[j]

    def summarize(self, first_row, first_turnon):
        rows, events = self.rows[first_row:], self.turnons[first_turnon:]
        duration = rows[-1]["t1_s"]-rows[0]["t0_s"]
        sums = {key: math.fsum(r[key] for r in rows) for key in (
            "source1_energy_j", "source2_energy_j", "resistor_energy_j", "diode_energy_j",
            "turnon_redistribution_energy_j", "inductor_charge_c", "integral_i2_a2_s")}
        change = rows[-1]["stored_energy1_j"]-rows[0]["stored_energy0_j"]
        return {"period_index": self.period_index, "i_start_a": rows[0]["i0_a"],
            "i_end_a": self.current, "periodic_current_difference_a": self.current-rows[0]["i0_a"],
            "p1_input_w": sums["source1_energy_j"]/duration,
            "p2_output_w": -sums["source2_energy_j"]/duration,
            "resistor_power_w": sums["resistor_energy_j"]/duration,
            "diode_power_w": sums["diode_energy_j"]/duration,
            "turnon_redistribution_power_w": sums["turnon_redistribution_energy_j"]/duration,
            "i_rms_a": math.sqrt(sums["integral_i2_a2_s"]/duration),
            "i_mean_a": sums["inductor_charge_c"]/duration,
            "i_peak_a": max(r["i_peak_a"] for r in rows),
            "leg_turnons": len(events), "zvs_in_model": sum(e["zvs_in_this_model"] for e in events),
            "stored_energy_change_j": change,
            "energy_residual_j": sums["source1_energy_j"]+sums["source2_energy_j"]-
                sums["resistor_energy_j"]-sums["diode_energy_j"]-sums["turnon_redistribution_energy_j"]-change,
            "integration_segments": len(rows)}

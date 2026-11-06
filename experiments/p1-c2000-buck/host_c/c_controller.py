"""Native host ABI binding; all control decisions execute in buck_control.c."""

import copy
import ctypes as ct

from buck_model import Parameters
from protection import ProtectedController, ProtectionLimits
from run_validation import CLEARS, STATES, fault_string


class BuckVoltagePI(ct.Structure):
    _fields_ = [("integral", ct.c_double)]


class BuckController(ct.Structure):
    _fields_ = [("pi", BuckVoltagePI), ("state", ct.c_int),
                ("latched_fault", ct.c_uint), ("start_sample", ct.c_uint64)]


class BuckCommand(ct.Structure):
    _fields_ = [("duty", ct.c_double), ("reference_v", ct.c_double),
                ("state", ct.c_int), ("active_faults", ct.c_uint),
                ("latched_fault", ct.c_uint), ("clear_result", ct.c_int)]


class BuckClearEvidence(ct.Structure):
    _fields_ = [("max_abs_output_v", ct.c_double), ("max_abs_current_a", ct.c_double),
                ("observable", ct.c_bool)]


def load_library(path):
    library = ct.CDLL(str(path))
    library.buck_controller_init.argtypes = [ct.POINTER(BuckController)]
    library.buck_controller_init.restype = None
    library.buck_controller_step.argtypes = [ct.POINTER(BuckController), ct.c_uint64,
                                           ct.c_double, ct.c_double, ct.c_double, ct.c_bool]
    library.buck_controller_step.restype = BuckCommand
    library.buck_controller_step_observed.argtypes = [*library.buck_controller_step.argtypes,
                                                     ct.POINTER(BuckClearEvidence)]
    library.buck_controller_step_observed.restype = BuckCommand
    return library


class CController:
    def __init__(self, library):
        self.library = library
        self.native = BuckController()
        library.buck_controller_init(ct.byref(self.native))
        self.p = Parameters()
        self.limits = ProtectionLimits()
        self.events = []
        self.main_step_calls = 0

    @property
    def state(self):
        return STATES[self.native.state]

    # Only the experiment harness uses this to schedule explicit test requests
    # and label true/measured eligibility. Native C independently detects faults.
    active_faults = ProtectedController.active_faults

    def __deepcopy__(self, memo):
        # The one hypothetical clear gets independent native state and events;
        # only the loaded function table is shared. It never drives the plant.
        shadow = object.__new__(type(self))
        shadow.library = self.library
        shadow.native = BuckController.from_buffer_copy(self.native)
        shadow.p = self.p
        shadow.limits = self.limits
        shadow.events = copy.deepcopy(self.events, memo)
        shadow.main_step_calls = 0
        return shadow

    def update(self, sample, input_v, output_v, current_a, clear_request=False, clear_evidence=None):
        old_state = self.state
        # This adapter is the ADC path. Missing evidence is deliberately NULL,
        # not inferred from decoded values or replaced by ideal plant truth.
        evidence = BuckClearEvidence(**clear_evidence) if clear_evidence is not None else None
        cmd = self.library.buck_controller_step_observed(ct.byref(self.native), sample,
                input_v, output_v, current_a, clear_request, ct.byref(evidence) if evidence is not None else None)
        self.main_step_calls += 1
        result = {"duty": cmd.duty, "reference_v": cmd.reference_v,
                  "state": STATES[cmd.state], "active_faults": fault_string(cmd.active_faults),
                  "latched_fault": fault_string(cmd.latched_fault), "clear_result": CLEARS[cmd.clear_result]}

        def event(before, after, reason, fault):
            self.events.append({"time_s": sample * self.p.control_period_s,
                                "from_state": before, "to_state": after,
                                "reason": reason, "latched_fault": fault})

        # Events are observation metadata, reconstructed from native results.
        if cmd.active_faults and old_state != "FAULT_LATCHED":
            event(old_state, "FAULT_LATCHED", "trip", result["latched_fault"])
        if cmd.clear_result in (1, 2, 3, 5):
            event("FAULT_LATCHED", result["state"], "clear_" + result["clear_result"], result["latched_fault"])
        if old_state == "SOFT_START" and result["state"] == "RUN":
            event(old_state, "RUN", "soft_start_complete", result["latched_fault"])
        return result

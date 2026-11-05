"""Read real TI object metadata/constants. This is NOT execution of C28x code."""
import argparse
import base64
import json
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "simulation"))
from buck_model import Parameters
from protection import ProtectionLimits


def inspect_results(output):
    probe = ET.parse(output / "numeric_probe.xml")
    image = ET.parse(output / "p1_image.xml")
    sections = {}
    for section in probe.findall(".//section_table/section"):
        name = section.findtext("elf32_shdr/sh_name_string")
        raw = section.findtext("raw_data")
        if raw:
            sections[name] = base64.b64decode(raw)
    values = struct.unpack("<6H", sections[".const:p1_numeric_format"])
    format_info = dict(zip(("char_bits", "float_bits", "double_bits", "float_radix", "float_mantissa_bits", "double_mantissa_bits"), values))
    p, limits = Parameters(), ProtectionLimits()
    expected = {
        "control_period_s": p.control_period_s, "kp": p.kp_duty_per_v,
        "ki_times_ts": p.ki_duty_per_v_s * p.control_period_s, "maximum_duty": p.maximum_duty,
        "overcurrent_a": limits.overcurrent_a, "overvoltage_v": limits.output_overvoltage_v,
        "undervoltage_v": limits.input_undervoltage_v, "clear_abs_v": limits.clear_max_abs_output_v,
        "clear_abs_a": limits.clear_max_abs_current_a,
        "ramp_at_999_samples_v": p.target_v * ((999 * p.control_period_s) / p.soft_start_s),
        "vin_raw2048_v": 2048 * (3.3 / 4096) * 10,
        "vout_raw1241_v": 1241 * (3.3 / 4096) * 2,
        "current_raw2048_a": (2048 * (3.3 / 4096) - 1.65) / 0.1,
        "current_raw2560_a": (2560 * (3.3 / 4096) - 1.65) / 0.1,
    }
    target = struct.unpack("<14d", sections[".const:p1_numeric_constants"])
    comparison = [{"quantity": name, "target_compiled_constant": actual,
                   "python_binary64": value, "difference": actual - value}
                  for (name, value), actual in zip(expected.items(), target)]
    machine = image.findtext(".//elf32_ehdr/e_machine")
    kind = image.findtext(".//elf32_ehdr/e_type")
    regions = []
    for line in (output / "p1_f280049c_ram.map").read_text().splitlines():
        fields = line.split()
        if len(fields) >= 6 and (fields[0].startswith(("RAM", "FLASH_")) or fields[0] == "BEGIN"):
            regions.append({"name": fields[0], "origin_words": int(fields[1], 16),
                            "capacity_words": int(fields[2], 16), "used_words": int(fields[3], 16)})
    map_text = (output / "p1_f280049c_ram.map").read_text()
    summary = {"probe_kind": "TI C28x object constants and ELF metadata; target code was NOT run",
               "machine": machine, "elf_type": kind,
               "entry_address": image.findtext(".//elf32_ehdr/e_entry"),
               "target_format": format_info,
               "host_format": {"char_bits": 8, "double_bits": struct.calcsize("d") * 8,
                               "double_mantissa_bits": sys.float_info.mant_dig},
               "comparison": comparison, "max_abs_constant_difference": max(abs(r["difference"]) for r in comparison),
               "constant_absolute_tolerance": 1e-14,
               "constant_tolerance_basis": "binary64 finite compile-time values, scale <= 16.5; allowance of a few binary64 rounding units; not a runtime controller tolerance",
               "memory_regions": regions,
               "total_allocated_ram_words_including_stack": sum(r["used_words"] for r in regions if not r["name"].startswith("FLASH_")),
               "allocated_flash_words": sum(r["used_words"] for r in regions if r["name"].startswith("FLASH_")),
               "linked_double_helpers": [name for name in ("__c28xabi_addd", "__c28xabi_mpyd", "__c28xabi_divd") if name in map_text],
               "timing_validation": "none; FPU32 target links software double helpers; no 20 us ISR claim"}
    (output / "numeric_and_image_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if values != (16, 32, 64, 2, 24, 53) or machine != "EM_TI_C2000" or kind != "ET_EXEC":
        raise AssertionError("Unexpected actual target format; evidence retained")
    if summary["max_abs_constant_difference"] > summary["constant_absolute_tolerance"]:
        raise AssertionError("Target constant representation differs; evidence retained")
    print(json.dumps({"target_format": format_info, "constants_compared": len(comparison),
                      "max_abs_difference": summary["max_abs_constant_difference"],
                      "allocated_ram_words_including_stack": summary["total_allocated_ram_words_including_stack"],
                      "allocated_flash_words": summary["allocated_flash_words"],
                      "machine": machine, "target_executed": False}), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="firmware/results")
    args = parser.parse_args()
    inspect_results((ROOT / args.output).resolve())

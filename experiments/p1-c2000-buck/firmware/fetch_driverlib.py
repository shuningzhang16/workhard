"""Download only F28004x build dependencies from the official versioned repository."""
import concurrent.futures
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG = "REL_C2000Ware_v26.02.00.00.LTS"
DEST = ROOT / ".tools" / "c2000ware-26.02"
BASE = f"https://raw.githubusercontent.com/TexasInstruments/c2000ware-core-sdk/{TAG}/"


def main():
    index = json.loads((ROOT / "evidence/target/official-subset-index.json").read_text())
    explicit = {"LICENSE.md", "README.md", "docs/manifest.html", "device_support/f28004x/common/include/device.h",
                "device_support/f28004x/common/include/driverlib.h",
                "device_support/f28004x/common/source/device.c",
                "device_support/f28004x/common/source/f28004x_codestartbranch.asm",
                "device_support/f28004x/common/cmd/28004x_generic_ram_lnk.cmd",
                "driverlib/f28004x/driverlib/ccs/Release/driverlib_eabi.lib"}
    paths = sorted(explicit | {e["path"] for e in index if
             e["path"].startswith("driverlib/f28004x/driverlib/") and e["path"].endswith(".h")})

    def fetch(path):
        target = DEST / path
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(BASE + path, timeout=40) as response:
                data = response.read()
            target.write_bytes(data)
            return {"path": path, "url": BASE + path, "bytes": len(data), "status": "downloaded"}
        except Exception as error:
            return {"path": path, "url": BASE + path, "status": "failed", "error": str(error)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(fetch, paths))
    (ROOT / "evidence/target/driverlib-downloads.json").write_text(json.dumps(results, indent=2) + "\n")
    failures = [r for r in results if r["status"] == "failed"]
    print(json.dumps({"version_tag": TAG, "files": len(results), "bytes": sum(r.get("bytes", 0) for r in results), "failures": failures}))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

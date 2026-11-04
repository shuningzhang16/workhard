"""从 TI 官方站点取得 Buck 原厂文件，仅保存到 Git 忽略的 vendor 目录。"""

import json
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PACKAGE = "C2000Ware_DigitalPower_SDK_26_01_00_00"
BASE = "https://dev.ti.com/tirex/content/"


def main():
    entries = json.loads((ROOT / "evidence/sdk-entries.json").read_text("utf-8"))
    paths = [
        entry["path"] for entry in entries
        if "/solutions/tidm_dc_dc_buck/" in entry["path"]
        and not entry["path"].endswith("/")
        and not entry["path"].endswith(".xlsx")
    ]
    paths += [f"{PACKAGE}/{name}" for name in (
        "license.txt", "docs/manifest.html", ".metadata/.tirex/package.tirex.json",
    )]
    results = []
    for path in paths:
        url = BASE + path
        target = ROOT / "vendor" / path
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read()
            status = response.status
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        results.append({"path": path, "url": url, "status": status, "bytes": len(data)})
        (ROOT / "evidence/download-results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{status} {len(data):7d} {path}", flush=True)
    print(f"Downloaded {len(results)} original files; no compilation or hardware execution.")


if __name__ == "__main__":
    main()

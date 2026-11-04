"""从 TI 官方站点取得 Buck 原厂文件，仅保存到 Git 忽略的 vendor 目录。"""

import json
import struct
import urllib.request
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PACKAGE = "C2000Ware_DigitalPower_SDK_26_01_00_00"
BASE = "https://dev.ti.com/tirex/content/"
ARCHIVE = (
    "https://downloads.ti.com/ccs/esd/tirex/zips/"
    f"{PACKAGE}/all/{PACKAGE}__all.zip"
)


def main():
    entries = json.loads((ROOT / "evidence/sdk-entries.json").read_text("utf-8"))
    selected = [
        entry for entry in entries
        if "/solutions/tidm_dc_dc_buck/" in entry["path"]
        and not entry["path"].endswith("/")
        and not entry["path"].endswith(".xlsx")
    ]
    # 公开静态内容服务器对 .cmd 返回 403；从官方公开 ZIP 读取同一例程。
    # 条目来自 ZIP 目录，读取该连续片段（约 350 kB），不下载整个 SDK。
    start = min(entry["offset"] for entry in selected)
    end = max(entry["offset"] + 30 + len(entry["path"].encode("utf-8"))
              + 65535 + entry["compressed"] for entry in selected)
    request = urllib.request.Request(ARCHIVE, headers={"Range": f"bytes={start}-{end-1}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 206:
            raise RuntimeError("服务器未返回分段内容，停止以免下载整套 SDK")
        block = response.read(end - start + 1)
    if len(block) != end - start:
        raise RuntimeError("下载片段长度不符")
    results = []
    for entry in selected:
        path = entry["path"]
        offset = entry["offset"] - start
        header = struct.unpack_from("<4s5H3L2H", block, offset)
        if header[0] != b"PK\x03\x04":
            raise ValueError(f"无效 ZIP 本地文件头: {path}")
        data_start = offset + 30 + header[9] + header[10]
        packed = block[data_start:data_start + entry["compressed"]]
        if entry["method"] == 8:
            data = zlib.decompress(packed, -15)
        elif entry["method"] == 0:
            data = packed
        else:
            raise ValueError(f"未支持 ZIP 压缩方法: {entry['method']}")
        if len(data) != entry["size"]:
            raise ValueError(f"解压长度不符: {path}")
        target = ROOT / "vendor" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        results.append({"path": path, "url": ARCHIVE, "status": 206, "bytes": len(data)})
        print(f"206 {len(data):7d} {path}", flush=True)
    for name in ("license.txt", "docs/manifest.html", ".metadata/.tirex/package.tirex.json"):
        path = f"{PACKAGE}/{name}"
        url = BASE + path
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read()
            status = response.status
        target = ROOT / "vendor" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        results.append({"path": path, "url": url, "status": status, "bytes": len(data)})
        print(f"{status} {len(data):7d} {path}", flush=True)
    (ROOT / "evidence/download-results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Downloaded {len(results)} original files; no compilation or hardware execution.")


if __name__ == "__main__":
    main()

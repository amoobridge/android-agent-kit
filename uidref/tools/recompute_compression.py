#!/usr/bin/env python3
"""从 data/ 的真机 XML 重算 uidref 的压缩比与可交互占比。

用法：
    python3 uidref/tools/recompute_compression.py

输出摘要行（供 CLAIMS.md 引用）：
    uidref 压缩 32.3x = V3（确定性计算，输入已提交）

不访问设备、不联网。任何人 clone 后可直接复现。
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uidref import parse_xml  # noqa: E402


def main() -> int:
    xmls = sorted((ROOT / "dumps").glob("*.xml"))
    if not xmls:
        print(f"错误：{ROOT / 'dumps'} 下没有 XML", file=sys.stderr)
        return 2

    total_xml = 0
    total_digest = 0
    total_nodes = 0
    total_actionable = 0

    for p in xmls:
        raw = p.read_text(encoding="utf-8", errors="replace")
        snap = parse_xml(raw)
        m = snap.metrics()
        total_xml += m["xml_bytes"]
        total_digest += m["digest_bytes"]
        total_nodes += m["nodes_total"]
        total_actionable += m["elements"]

    ratio = total_xml / total_digest if total_digest else 0.0
    pct = total_actionable / total_nodes * 100 if total_nodes else 0.0

    print("=" * 66)
    print("uidref · 压缩比与可交互占比复算（输入 = dumps/ 下已提交的 XML）")
    print("=" * 66)
    print(f"  界面数          {len(xmls)}")
    print(f"  XML 合计        {total_xml} B")
    print(f"  digest 合计     {total_digest} B")
    print(f"  压缩比          {ratio:.1f}x")
    print(f"  节点合计        {total_nodes}")
    print(f"  可交互合计      {total_actionable}（{pct:.1f}%）")
    print()
    print("README 声称：276 KB / 8.6 KB = 32.3x，789 节点中 132 可交互（16.7%）")
    print(f"本次复算    ：{total_xml/1024:.0f} KB / {total_digest/1024:.1f} KB "
          f"= {ratio:.1f}x，{total_nodes} 节点中 {total_actionable} 可交互（{pct:.1f}%）")
    print()
    if abs(ratio - 32.3) > 0.15:
        print("⚠ 压缩比与 README 不一致")
    if abs(pct - 16.7) > 0.1:
        print("⚠ 可交互占比与 README 不一致（已把 17.3% 更正为 16.7%）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

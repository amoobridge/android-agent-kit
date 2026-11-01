"""claimaudit CLI：扫全部资产的量化声明，输出审计表。

用法：
    python tools/audit_claims.py            人读摘要
    python tools/audit_claims.py --json     输出到 data/audit.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core import (load_ledger, summary, verify_ledger,
                  citable_but_should_not, refuted_but_citable)

DATA = Path(__file__).resolve().parent.parent / "data" / "evidence_ledger.json"


def main() -> int:
    rows = load_ledger(DATA)
    s = summary(rows)

    print("=" * 72)
    print("claimaudit · 量化声明证据台账")
    print("=" * 72)
    print(f"声明 {s['total']} 条 · 覆盖 {len(s['assets'])} 个资产")
    print(f"  by_level  {s['by_level']}")
    print(f"  citable {s['citable']} · not_citable {s['not_citable']}")

    problems = verify_ledger(rows)
    print(f"\n复算不一致: {len(problems)}")
    for p in problems:
        print(f"  ✗ {p['id']}  台账={p['declared']} 复算={p['computed']}  ({p['why']})")

    bad = citable_but_should_not(rows) + refuted_but_citable(rows)
    print(f"硬规则违反: {len(bad)}")
    for r in bad:
        print(f"  ✗ {r.id}  level={r.level} citable={r.citable}")

    print("\n--- 不可引用的声明（必须带标注）---")
    for r in rows:
        if not r.citable:
            print(f"  [{r.asset}] {r.claim[:60]}")
            print(f"      level={r.level}  原因: {r.note[:76]}")

    if "--json" in sys.argv:
        out = Path(__file__).resolve().parent.parent / "data" / "audit.json"
        out.write_text(json.dumps(
            {"summary": s,
             "problems": problems,
             "rows": [{"id": r.id, "asset": r.asset, "claim": r.claim,
                       "level": r.level, "citable": r.citable,
                       "observations": r.observations, "states": r.states,
                       "channels": r.channels, "deterministic": r.deterministic,
                       "note": r.note} for r in rows]},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已存证 → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

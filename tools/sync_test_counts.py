#!/usr/bin/env python3
"""sync_test_counts.py —— 文档里写死的测试数 vs 实际跑出来的数。

## 为什么需要这个工具

测试数是**派生值**，却被抄成文档里的**手写字面量**。
加了测试不会自动更新文档——于是文档开始说谎，而且没人报警。

这不是假想。本项目实测抓到过三轮：

| 轮次 | 抓到什么 |
|---|---|
| | 顶层 README 测试数全是人记忆里的旧值 |
| | 元测试写死「静默 7 条」没随 SPEC 分类调整同步 |
| | README 表格 5 处测试数不对 |
| **** | **本套件 10 处写死数字与实际不符** |

共同根因：**数字抄进文档的那一刻就开始腐化。**

## 这个工具做什么

逐个库跑 pytest 拿真实条数，再与 README/SPEC 里写的数字比对。
不一致就报出来，退出码非零——可以直接挂进 run-tests.sh。

## 诚实边界

1. **只查「N 条 pytest / N passed」这种显式声称**，不猜语义。
   文档里其他数字（向量数、节点数、百分比）不在管辖范围——
   那些由各自的 `docs/CLAIMS.md` 与复算工具管。
2. **允许「≥」表述**：写「42+ 条」或「≥42 条」不报错，
   因为那是在声称下界，不是声称精确值。
3. **跨库 skip 不计入**：`PRESENT` 之外的兄弟库相关测试是 skip，
   工具按「passed」计，不按「collected」计——skip 的设备相关测试
   不该让文档数字虚高。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

# 只查本套件中实际存在的库
LIBS = [
    "uidref", "scrollkey", "fieldstate", "imespec", "blindspot",
    "screenpoint", "pointparse", "textin", "swipefind",
    "screendiff", "crosstrack",
    "claimcheck", "claimaudit", "capturetrap",
]

# 匹配显式的「全库测试条数」声称。
# 注意：只认带 pytest / passed / "# N 条" 的形态。
# **不认裸的「N 条测试」**——那常指某个具体文件的条数
# （如「test_capture_fallback.py 5 条测试守着」，5 是对的），
# 不是全库总数。第一版工具在这里误报过一条。
PATTERNS = [
    re.compile(r"(\d+)\s*条\s*pytest"),
    re.compile(r"(\d+)\s*passed"),
    re.compile(r"#\s*(\d+)\s*条"),
]


def actual_count(lib: str) -> int | None:
    """跑该库的测试，拿 passed 数。失败返回 None。"""
    d = ROOT / lib
    if not (d / "tests").is_dir():
        return None
    r = subprocess.run(
        [PY, "-m", "pytest", "tests", "-q"],
        cwd=d, capture_output=True, text=True, timeout=300,
    )
    m = re.search(r"(\d+)\s+passed", r.stdout + r.stderr)
    return int(m.group(1)) if m else None


def doc_claims(lib: str) -> list[tuple[str, int, int]]:
    """返回 [(文件, 行号, 声称的条数)]"""
    out = []
    for name in ("README.md", "SPEC.md"):
        p = ROOT / lib / name
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if not re.search(r"pytest|passed|测试", line, re.I):
                continue
            # 跳过「≥42」「42+」这类下界表述
            if re.search(r"[≥>]\s*\d+\s*条|\d+\s*\+\s*条", line):
                continue
            for pat in PATTERNS:
                m = pat.search(line)
                if m:
                    out.append((name, i, int(m.group(1))))
                    break
    return out


def main() -> int:
    bad = []
    print("=== 文档写死的测试数 vs 实测 ===")
    print(f"{'库':<14}{'实测':>6}  文档声称")
    print("-" * 60)
    for lib in LIBS:
        real = actual_count(lib)
        if real is None:
            continue
        claims = doc_claims(lib)
        wrong = [(f, ln, n) for f, ln, n in claims if n != real]
        shown = ", ".join(f"{f}:{ln}={n}" for f, ln, n in claims) or "—"
        mark = "❌" if wrong else "✅"
        print(f"{lib:<14}{real:>6}  {mark} {shown}")
        for f, ln, n in wrong:
            bad.append((lib, f, ln, n, real))

    print("-" * 60)
    if bad:
        print(f"\n❌ {len(bad)} 处文档数字与实际不符：")
        for lib, f, ln, n, real in bad:
            print(f"   {lib}/{f}:{ln}  写 {n}，实际 {real}")
        print("\n修法：改文档，或把该处改成指向本工具。")
        return 1
    print("✅ 全部一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())

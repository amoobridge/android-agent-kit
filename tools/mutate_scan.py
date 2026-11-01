#!/usr/bin/env python3
"""库级变异扫描：把每个库的核心算法改坏，验证该库的测试**必须失败**。

为什么需要这个
--------------
「N 条测试通过」这个数字本身需要一个判据。没有它，测试可能全是空转：
uidref 曾有 12 条向量因为生成器 bug 一条都没测到声称的规则，
screendiff 的元测试第一版太强/太弱，fieldstate 的 D2 聚焦分支
42 条测试全绿而实现被改成恒 false 也全绿。

已有的防线：
  - 逐用例空转检查（TestNotVacuous 元测试）
  - verify_impl.py 的 4 种破坏形态（对外部实现）
这个工具补上第三层：**对库自己的实现做变异**。

用法
----
    python3 tools/mutate_scan.py            # 扫全部
    python3 tools/mutate_scan.py uidref     # 只扫一个库

变异分两类：
  1. 改名变异（import 断）——弱，只证明测试会加载代码
  2. 真算法变异（import 不断，语义变）——强，证明测试断言了行为

退出码：0 = 全部抓住；1 = 有逃逸。
"""
from __future__ import annotations

import atexit
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = os.environ.get("PYTHON", "python3")
# 本工具会在各库目录里起子进程，相对路径的 PY 在那里解析不到。
# 实测：PYTHON=.venv/bin/python3 时 pytest 段通过、本工具报
#   FileNotFoundError: '.venv/bin/python3'
# run-tests.sh 已导出绝对路径，这里再兜一层，单独跑也不会踩。
if not PY.startswith("/"):
    PY = str((Path.cwd() / PY).resolve()) if "/" in PY else shutil.which(PY) or PY

# ---------------------------------------------------------------------------
# 真算法变异（import 不断，语义变）——这些才是有判据的
# (库, 相对路径, 原文, 变异, 说明)
# ---------------------------------------------------------------------------
ALGO: list[tuple[str, str, str, str, str]] = [
    # uidref
    # 用单行做变异锚点：多行原文对缩进/空白敏感，SKIP 率高
    ("uidref", "uidref/uidref/digest.py",
     '    if _t(node, "class").rsplit(".", 1)[-1].endswith("EditText"):',
     '    if False and _t(node, "class").rsplit(".", 1)[-1].endswith("EditText"):',
     "EditText 可交互判定被短路"),
    ("uidref", "uidref/uidref/digest.py",
     '    if _flag(node, "scrollable"):',
     '    if _flag(node, "scrollable") and False:',
     "scrollable 可交互判定被短路"),
    ("uidref", "uidref/uidref/digest.py",
     '    if _flag(node, "clickable"):',
     '    if _flag(node, "clickable") and False:',
     "clickable 可交互判定被短路"),
    # screendiff：真机事故的修复点
    ("screendiff", "screendiff/screendiff/core.py",
     "    if ov >= 0.8 and _size_ratio(p, c) >= 0.5:",
     "    if ov >= 0.8 and _size_ratio(p, c) >= 0.1:",
     "面积比闸门 0.5→0.1（真机事故修复点）"),
    ("screendiff", "screendiff/screendiff/core.py",
     "    if p.class_name and p.class_name == c.class_name and ov >= 0.5:",
     "    if p.class_name and p.class_name == c.class_name and ov >= 0.5 and False:",
     "rid 主导匹配被短路"),
    # fieldstate：的真 bug 修复点
    ("fieldstate", "fieldstate/core.py",
     '        focused = "true" if d["is_focused"] else "false"',
     '        focused = "false"',
     "is_focused 恒 false（逃逸点）"),
    ("fieldstate", "fieldstate/core.py",
     "    if st.focused is not None:\n"
     '        if st.focused == "true":\n            return "focused"\n'
     '        if st.focused == "false":\n            return "unfocused"\n'
     "    if st.api_is_focused is not None:\n"
     '        return "focused" if st.api_is_focused else "unfocused"\n'
     '    return "unknown"',
     "    if st.api_is_focused is not None:\n"
     '        return "focused" if st.api_is_focused else "unfocused"\n'
     '    return "unknown"',
     "优先级改回旧顺序（bug 复发）"),
    # imespec
    ("imespec", "imespec/core.py",
     '        return "reachable"',
     '        return "blocked"',
     "可及性判定反了"),
    # claimcheck
    ("claimcheck", "claimcheck/core.py",
     "    V1_REPEATED = 1      # 同一起始状态复现 >= 3 次",
     "    V1_REPEATED = 99     # 同一起始状态复现 >= 3 次",
     "V1 阈值 1→99"),
    # imespec：的 SPEC 条件覆盖
    ("imespec", "imespec/core.py",
     "    return element.overlap(ime) / a",
     "    return 1.0 if element.y1 >= ime.y1 else 0.0",
     "遮挡比改用 y 坐标比较（SPEC C4）"),
    ("imespec", "imespec/core.py",
     "        x1, y1 = (int(v) for v in parts[0].split(\",\"))",
     "        x1, y1 = (int(v) for v in parts[0])",
     "★ parse_bounds 把逗号当分隔符（SPEC C6 的坑）"),
    ("imespec", "imespec/core.py",
     '    return element.overlap(ime) / a',
     '    return element.overlap(ime) / (a + 1)',
     "遮挡比分母 +1（边界：恰好 1.0 不再成立）"),
    # blindspot：的 SPEC 条件覆盖
    ("blindspot", "blindspot/core.py",
     "        x1, y1 = (int(v) for v in p[0].split(\",\"))",
     "        x1, y1 = (int(v) for v in p[0])",
     "★ parse_bounds 把逗号当分隔符（SPEC C6）"),
    # fieldstate：的 SPEC 条件覆盖
    ("fieldstate", "fieldstate/core.py",
     "    if st.focused is not None:",
     "    if st.focused is not None and False:",
     "★ D2 忽略归一 focused 字段（修复回退）"),
    ("fieldstate", "fieldstate/core.py",
     "    return st.text is not None",
     "    return st.is_showing_hint_text is not None",
     "★ D4 改依赖 D1 判据（SPEC C6）"),
    # textin：证据复算——数据驱动的测试，变异数据即变异测试
    ("textin", "textin/tests/test_evidence.py",
     'def _silent_failures() -> list[dict]:\n'
     '    """退出码 0、stderr 空、结果不符——真正的静默失败。\n\n'
     '    反引号那一行 rc=0 但 stderr 非空，**不算**这一类（见第三类）。\n'
     '    """\n'
     '    return [r for r in PROBE["results"]\n'
     '            if r["adb_rc"] == 0 and not r["adb_stderr"].strip()\n'
     '            and r["got"] != r["input"]]',
     'def _silent_failures() -> list[dict]:\n'
     '    return [r for r in PROBE["results"]\n'
     '            if r["adb_rc"] == 0 and not r["adb_stderr"].strip()]',
     "静默失败判定丢掉「结果不符」条件（第三类边界）"),
    ("textin", "textin/tests/test_evidence.py",
     '    assert len(verdicts) == 3, f"verdict 应为 3 个取值，实际 {verdicts}"',
     '    assert len(verdicts) == 2, f"verdict 应为 3 个取值，实际 {verdicts}"',
     "三分法断言改成二分（SPEC C2）"),
    ("textin", "textin/data/probe_results.json",
     '"adb_rc": 0,\n      "adb_stderr": "/system/bin/sh: b: inaccessible or not found"',
     '"adb_rc": 0,\n      "adb_stderr": ""',
     "★ 反引号 stderr 被清空（第三类依据消失）"),
    # capturetrap
    ("capturetrap", "capturetrap/core.py",
     "def is_valid_capture(raw: bytes) -> bool:",
     "def _unused_is_valid_capture(raw: bytes) -> bool:",
     "合法性判定改名"),
    # blindspot
    ("blindspot", "blindspot/core.py",
     "def verify_blind_in_screenshot",
     "def _unused_verify_blind_in_screenshot",
     "截图校验函数改名", "pil"),
    # swipefind
    ("swipefind", "swipefind/core.py",
     "def is_exhausted",
     "def _unused_is_exhausted",
     "触底判定改名"),
    # pointparse
    ("pointparse", "pointparse/pointparse/parse.py",
     "def _find_all_pairs(text: str) -> list[tuple[float, float]]:",
     "def _unused_find_all_pairs(text: str) -> list[tuple[float, float]]:",
     "文本指点解析改名"),
    # screenpoint
    ("screenpoint", "screenpoint/screenpoint/mapping.py",
     "def map_point(p: Point, src: CoordinateSpace, dst: CoordinateSpace, *, fit: FitMode) -> Point:",
     "def _unused_map_point(p: Point, src: CoordinateSpace, dst: CoordinateSpace, *, fit: FitMode) -> Point:",
     "坐标映射改名"),
    # crosstrack
    ("crosstrack", "crosstrack/crosstrack.py",
     "def audit_diff",
     "def _unused_audit_diff",
     "跨页审计改名"),
    # scrollkey
    ("scrollkey", "scrollkey/scrollkey.py",
     "def base_key(el: Element) -> str:",
     "def _unused_base_key(el: Element) -> str:",
     "基键构造改名"),
    # claimaudit
    ("claimaudit", "claimaudit/core.py",
     "def verify_ledger",
     "def _unused_verify_ledger",
     "台账复算改名"),
]

# ---------------------------------------------------------------------------
# JS 侧变异：跨语言一致性声明（uidref 45×2 / screendiff 27×2）靠这两个实现
# (库, 相对路径, 原文, 变异, 说明)
# ---------------------------------------------------------------------------
JS: list[tuple[str, str, str, str, str]] = [
    ("uidref", "js/uidref.js",
     "  if (flag(node, 'clickable')) return true;",
     "  return false;",
     "isActionable 恒 false"),
    ("uidref", "js/uidref.js",
     "  return { x: Math.floor((b.x1 + b.x2) / 2), y: Math.floor((b.y1 + b.y2) / 2) };",
     "  return { x: Math.trunc((b.x1 + b.x2) / 2), y: Math.trunc((b.y1 + b.y2) / 2) };",
     "★ centerOf floor→trunc（SPEC A1 明确禁止）"),
    ("uidref", "js/uidref.js",
     "  return { x: Math.floor((b.x1 + b.x2) / 2), y: Math.floor((b.y1 + b.y2) / 2) };",
     "  return { x: ((b.x1 + b.x2) / 2 | 0), y: ((b.y1 + b.y2) / 2 | 0) };",
     "★ centerOf floor→|0（SPEC A1 陷阱）"),
    ("uidref", "js/uidref.js",
     "  return simpleClass(node).endsWith('EditText');",
     "  return false;",
     "EditText 判定被短路"),
    ("screendiff", "js/screendiff.js",
     "  if (ov >= 0.8 && sizeRatio(p, c) >= 0.5) return 20;",
     "  if (ov >= 0.8 && sizeRatio(p, c) >= 0.1) return 20;",
     "★ 面积比闸门 0.5→0.1（真机事故修复点）"),
    ("screendiff", "js/screendiff.js",
     "  if (p.class_name && p.class_name === c.class_name && ov >= 0.5) return 50;",
     "  if (p.class_name && p.class_name === c.class_name && ov >= 0.5 && false) return 50;",
     "★ rid 主导匹配被短路"),
    ("screendiff", "js/screendiff.js",
     "  if (ov >= 0.8 && sizeRatio(p, c) >= 0.5) return 20;",
     "  if (ov >= 0.8 && sizeRatio(p, c) >= 0.5 && false) return 20;",
     "几何 tier 被短路"),
]


# ---------------------------------------------------------------------------
# 崩溃安全：变异是「改坏 → 跑测试 → 恢复」。任何一步被打断，
# 源码就留在被改坏的状态——本次实测踩到过（工具层 60s 超时 SIGKILL
# subprocess，finally 没跑，`scrollable and False` 残留在文件里）。
#
# 三层保护：
#   ① atexit      —— 正常退出 / sys.exit 时恢复
#   ② SIGTERM/INT —— 被 kill 时恢复（SIGKILL 救不了，见下）
#   ③ 启动时自检  —— 上次残留的变异，这次先扫出来
# ---------------------------------------------------------------------------
_BACKUP: dict[Path, str] = {}


def _backup(path: Path) -> str:
    if path not in _BACKUP:
        _BACKUP[path] = path.read_text(encoding="utf-8")
    return _BACKUP[path]


def _restore_all() -> None:
    for path, text in list(_BACKUP.items()):
        try:
            if path.exists() and path.read_text(encoding="utf-8") != text:
                path.write_text(text, encoding="utf-8")
                print(f"⚠️  已恢复被中断的变异：{path.relative_to(ROOT)}")
        except OSError:
            pass
    _BACKUP.clear()


atexit.register(_restore_all)


def _on_signal(signum, frame):     # noqa: ARG001
    _restore_all()
    sys.exit(128 + signum)


for _sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    try:
        signal.signal(_sig, _on_signal)
    except (ValueError, OSError):
        pass


def scan_leftover_mutations() -> list[tuple[Path, str, str, str]]:
    """启动时自检：所有变异锚点的原文是否都在。

    上次被 SIGKILL 打断会留下 `scrollable and False` 这类残留
    （本次实测踩到：工具层 60s 超时 SIGKILL subprocess，finally 没跑）。
    不清掉的话，后续所有测试跑的都是变异代码——而且看起来像"测试失败了"。

    返回 (路径, 变异串, 原文, 说明)，调用方可直接反向替换恢复。
    """
    bad = []
    for item in ALGO + JS:
        lib, rel, orig, mut, desc = item[:5]
        p = ROOT / lib / rel if rel.startswith("js/") else ROOT / rel
        if not p.exists():
            continue
        cur = p.read_text(encoding="utf-8")
        if orig not in cur and mut in cur:
            bad.append((p, mut, orig, f"{lib}: {desc}"))
    return bad


def clear_pyc_all() -> None:
    for cache in ROOT.rglob("__pycache__"):
        if "node_modules" not in str(cache):
            shutil.rmtree(cache, ignore_errors=True)


def clear_pyc(lib: str) -> None:
    """清掉该库的 __pycache__。

    ★ 的真 bug：变异写文件 → 跑 pytest → 原样写回，
    三步在同一秒内完成时，Python 按 mtime 判断 pyc 是否失效——
    mtime 相同 → **复用变异期间编译的 pyc**。

    实测（claimcheck）：
        变异期间            MIN = 99
        恢复后（未清 pyc）  MIN = 99   ← 源码已还原，导入的却是变异版
        清 pyc 后          MIN = 1

    后果：变异扫描「恢复」后，后续跑到的测试用的是变异代码。
    本次表现为 claimaudit 突然 1 failed，而源码完全干净。
    """
    d = ROOT / lib
    for cache in d.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def run_py(lib: str) -> tuple[int, str]:
    r = subprocess.run(
        [PY, "-m", "pytest", "tests", "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=ROOT / lib, capture_output=True, text=True, timeout=600)
    return r.returncode, (r.stdout.strip().splitlines() or [""])[-1]


def run_js(lib: str) -> tuple[int, str]:
    r = subprocess.run(
        ["node", "js/conformance.js", "vectors/"],
        cwd=ROOT / lib, capture_output=True, text=True, timeout=300)
    out = r.stdout.strip().splitlines()
    return r.returncode, (out[-1] if out else r.stderr.strip()[:60])


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    leftover = scan_leftover_mutations()
    if leftover:
        print("=" * 78)
        print("⚠️  检测到上次中断残留的变异，已反向恢复：")
        for path, mut, orig, desc in leftover:
            cur = path.read_text(encoding="utf-8")
            path.write_text(cur.replace(mut, orig, 1), encoding="utf-8")
            print(f"   - {desc}")
            print(f"     {path.relative_to(ROOT)}: {mut.strip()[:50]} → {orig.strip()[:50]}")
        clear_pyc_all()
        print("=" * 78)
    print("=" * 78)
    print("库级变异扫描 · 测试能否抓住被改坏的实现")
    print("=" * 78)

    escaped: list[tuple[str, str]] = []
    unverified: list[tuple[str, str]] = []
    total = 0
    try:
        import PIL  # noqa: F401
        _has_pil = True
    except ImportError:
        _has_pil = False

    for item in ALGO:
        lib, rel, orig, mut, desc = item[:5]
        needs = item[5] if len(item) > 5 else None
        if only and lib != only:
            continue
        total += 1
        p = ROOT / rel
        if not p.exists() or orig not in p.read_text(encoding="utf-8"):
            print(f"SKIP   {lib:<12} {desc}")
            continue
        if needs == "pil" and not _has_pil:
            print(f"⏭ 未验证  {lib:<12} {desc:<40} 缺 Pillow，守卫测试被 skip")
            unverified.append((lib, desc))
            continue
        s = _backup(p)
        p.write_text(s.replace(orig, mut, 1), encoding="utf-8")
        try:
            rc, last = run_py(lib)
        except subprocess.TimeoutExpired:
            rc, last = -1, "TIMEOUT"
        finally:
            p.write_text(s, encoding="utf-8")   # 无论如何恢复
            clear_pyc(lib)                      # pyc 不会自行失效
        v = "✅ 抓住" if rc != 0 else ("⏱ 超时" if rc == -1 else "❌ 逃逸")
        if v == "❌ 逃逸":
            escaped.append((lib, desc))
        print(f"{v}  {lib:<12} {desc:<40} {last[:34]}")

    for lib, rel, orig, mut, desc in JS:
        if only and lib != only:
            continue
        total += 1
        p = ROOT / lib / rel
        if not p.exists() or orig not in p.read_text(encoding="utf-8"):
            print(f"SKIP   {lib:<12} {desc}")
            continue
        s = _backup(p)
        p.write_text(s.replace(orig, mut, 1), encoding="utf-8")
        try:
            rc, last = run_js(lib)
        except subprocess.TimeoutExpired:
            rc, last = -1, "TIMEOUT"
        finally:
            p.write_text(s, encoding="utf-8")
            clear_pyc(lib)
        v = "✅ 抓住" if rc != 0 else ("⏱ 超时" if rc == -1 else "❌ 逃逸")
        if v == "❌ 逃逸":
            escaped.append((lib + "/js", desc))
        print(f"{v}  {lib + '/js':<12} {desc:<40} {last[:34]}")

    print("-" * 78)
    print(f"变异 {total} 个 · 逃逸 {len(escaped)} · 未验证 {len(unverified)}")
    for lib, desc in escaped:
        print(f"  ❌ {lib}: {desc} —— 该库测试在实现被改坏时仍然全绿")
    for lib, desc in unverified:
        print(f"  ⏭ {lib}: {desc} —— 缺 Pillow，本次未验证（pip install -r requirements.txt）")
    if unverified:
        print("\n⚠️  有变异未验证：「逃逸 0」只覆盖本次实际跑过的部分。")
    return 1 if escaped else 0


if __name__ == "__main__":
    sys.exit(main())

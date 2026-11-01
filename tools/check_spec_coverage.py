"""SPEC 一致性条件 ↔ 测试覆盖 的对应检查。

为什么需要这个
--------------
textin 的 SPEC 有 8 条强制约束，但没有任何测试从数据复算它们——
**SPEC 声称的约束与测试之间没有判据**。

本检查把这件事系统化：对每个库，抽出 SPEC 的 C1..Cn，
用**人工核验过的关键词**在测试里找对应断言，报告缺口。

关键词是人工核验过的（逐个看过测试正文），不是自动猜的——
第一版自动关键词扫描报了 40 个缺口，实际只有 9 个是真的，
其余 31 个是关键词没匹配上（测试用了别的表述）。

用法：
    python tools/check_spec_coverage.py          人读摘要
    python tools/check_spec_coverage.py --json   存证
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 人工核验过的覆盖映射：(库, 条件号) -> (关键词列表, 说明)
# 关键词命中任意一个即算覆盖。空列表 = 已知无测试覆盖（真缺口）。
COVERAGE: dict[tuple[str, str], tuple[list[str], str]] = {
    # ---- uidref ----
    ("uidref", "C1"): (["golden_vector", "conformance"], "黄金向量运行器"),
    ("uidref", "C2"): (["ELEMENT_FIELDS", "字段集合"], "契约字段比对"),
    ("uidref", "C3"): (["test_snapshot_id_deterministic", "digest_is_deterministic"],
                       "确定性"),
    ("uidref", "C4"): (["test_real_dumps_agree_across_languages"],
                       "真实 dump 跨语言一致"),
    # ---- screendiff ----
    ("screendiff", "C1"): (["test_vectors_match_implementation"], "黄金向量"),
    ("screendiff", "C2"): (["契约", "ELEMENT_FIELDS"], "契约字段"),
    ("screendiff", "C3"): (["test_idempotent"], "幂等"),
    ("screendiff", "C4"): (["test_real_dumps_agree_across_languages"], "真实 dump"),
    # ---- imespec ----
    ("imespec", "C1"): (["unknown"], "无 IME 时报 unknown"),
    ("imespec", "C3"): (["AccessibilityWindowInfo"], "窗口信息"),
    ("imespec", "C4"): (["面积", "by_area", "area_ratio"],
                        "★ 缺口候选：遮挡比按面积算"),
    ("imespec", "C5"): (["1.0", "exactly"], "★ 缺口候选：遮挡比恰 1.0 判 occluded"),
    ("imespec", "C6"): (["逗号", "comma", "0,1548"],
                        "★ 缺口候选：parse_bounds 内部逗号"),
    # ---- blindspot ----
    ("blindspot", "C5"): (["面积", "by_area"], "★ 缺口候选：重叠用面积"),
    ("blindspot", "C6"): (["逗号", "comma"], "★ 缺口候选：parse_bounds 逗号"),
    ("blindspot", "C7"): (["不一致", "mismatch", "disagree"],
                          "★ 缺口候选：截图与 IME 不一致时显式报告"),
    # ---- swipefind ----
    ("swipefind", "C1"): (["起点"], "吸收判据是起点"),
    ("swipefind", "C2"): (["线段", "segment", "Liang"],
                          "★ 缺口候选：线段-矩形相交"),
    ("swipefind", "C3"): (["window"], "window>=2"),
    ("swipefind", "C4"): (["0,1548", "comma", "逗号", "内部"],
                          "★ 缺口：parse_bounds 内部逗号"),
    ("swipefind", "C5"): (["复位"], "复位可验证"),
    ("swipefind", "C6"): (["非单调", "too_long"], "长度非单调"),
    # ---- capturetrap ----
    ("capturetrap", "C1"): (["returncode", "looks_like_unknown_command"],
                            "adb 报错不得看起来像抓取成功"),
    ("capturetrap", "C2"): (["decode", "binary"], "二进制 + replace"),
    ("capturetrap", "C3"): (["find(", "startswith"], "find>=0"),
    ("capturetrap", "C4"): (["rm -f", "内容签名", "签名"],
                            "dump 前 rm -f + 内容签名判新"),
    # ---- claimcheck ----
    ("claimcheck", "C1"): (["classify("], "三参数分别计量"),
    ("claimcheck", "C2"): (["should_verify_before_writing"], "单次观测触发"),
    ("claimcheck", "C3"): (["original_observation"], "refute 保留原始观测"),
    ("claimcheck", "C4"): (["citable"], "V4 不可引用"),
    ("claimcheck", "C5"): (["required_marker"], "标记文案"),
    # ---- claimaudit ----
    ("claimaudit", "C1"): (["verify_ledger"], "复算排除 V4"),
    ("claimaudit", "C2"): (["effective_level"], "替代解释降 V0"),
    ("claimaudit", "C3"): (["effective_level", "deterministic"], "deterministic 至少 V1"),
    ("claimaudit", "C4"): (["citable_but_should_not"], "一致性检查函数"),
    ("claimaudit", "C5"): (["refuted_but_citable"], "一致性检查函数"),
    # ---- imespec / blindspot / fieldstate 缺口补齐后的断言关键词 ----
    ("imespec", "C4"): (["面积", "by_area", "area_ratio"], "遮挡比按面积算"),
    ("imespec", "C5"): (["1.0", "exactly", "恰"], "遮挡比恰 1.0 判 occluded"),
    ("imespec", "C6"): (["逗号", "comma", "0,1548"], "parse_bounds 内部逗号"),
    ("blindspot", "C5"): (["面积", "by_area"], "重叠用面积"),
    ("blindspot", "C6"): (["逗号", "comma"], "parse_bounds 逗号"),
    ("fieldstate", "C6"): (["d4_reliable", "不同判据"],
                           "D4 与 D1 不同判据"),
    ("fieldstate", "C7"): (["字段名", "field_name", "state_from_api"],
                           "API JSON 字段名"),
    # ---- textin ----
    ("textin", "C1"): (["baseline", "hint"], "不得假设空字段 text 为空"),
    ("textin", "C2"): (["verdict", "三分"], "三分法"),
    ("textin", "C3"): (["focused"], "输入前验证 focused"),
    ("textin", "C4"): (["before", "基线"], "输入前回到基线"),
    ("textin", "C5"): (["adb_rc", "adb_stderr"], "记退出码与 stderr"),
    ("textin", "C6"): (["third_class", "第三类"], "三类区分"),
    ("textin", "C7"): (["b_set_text", "b_ok"], "分开证传输层与 API"),
    ("textin", "C7a"): (["base64"], "base64 传输"),
    # ---- imespec 补登记 ----
    ("imespec", "C2"): (["TYPE_INPUT_METHOD", "type"], "识别 IME 用 type 不用标题"),
    ("imespec", "C3"): (["AccessibilityWindowInfo"], "窗口信息"),
    # ---- blindspot 补登记 ----
    ("blindspot", "C1"): (["TYPE_INPUT_METHOD", "type"], "识别 IME 用 type"),
    ("blindspot", "C2"): (["未验证", "unverified", "不得凭推测", "不得"],
                          "不得凭推测加窗口类型"),
    ("blindspot", "C3"): (["app_reference", "参考区域", "XML 错"],
                          "截图是参考通道"),
    ("blindspot", "C3"): (["参考通道", "XML 错", "reference"],
                          "截图是参考通道"),
    ("blindspot", "C4"): (["None", "screenshot_agrees"],
                          "无截图时报 None"),
    ("blindspot", "C7"): (["不一致", "mismatch"],
                          "截图与 IME 不一致时报告"),
    # ---- fieldstate 补登记 ----
    ("fieldstate", "C3"): (["isEditable", "is_editable"], "isEditable"),
    ("fieldstate", "C4"): (["空文本", "empty", "不得"], "清场不依赖空文本"),
    ("fieldstate", "C5"): (["不再变化", "converge", "收敛"], "清场收敛判据"),
    # ---- fieldstate ----
    ("fieldstate", "C1"): (["hint", "isShowingHint"], "不得只用 text 判空"),
    ("fieldstate", "C2"): (["focusable"], "★ 用 focused 不用 focusable"),
    ("fieldstate", "C7"): (["字段名", "field_name"],
                           "★ 缺口候选：API JSON 字段名"),
    ("fieldstate", "C8"): (["focused"], "归一字段优先于原始布尔"),
}

# 自检：COVERAGE 不允许重复键（Python 字典会静默取最后一个，
# 导致先登记的覆盖被后登记的顶掉——实际踩到）
_seen: set[tuple[str, str]] = set()
for _k in list(COVERAGE):
    assert _k not in _seen, f"COVERAGE 有重复键 {_k}"
    _seen.add(_k)

LIBS = ["uidref", "screendiff", "imespec", "blindspot", "swipefind",
        "capturetrap", "claimcheck", "claimaudit", "textin", "fieldstate"]


def _test_text(lib: str) -> str:
    """收集该库测试与自检工具的源码文本。"""
    out = []
    for sub in ("tests", "tools"):
        d = ROOT / lib / sub
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.py")):
            try:
                out.append(f.read_text(encoding="utf-8"))
            except Exception:
                pass
    return "\n".join(out)


def _spec_conditions(lib: str) -> list[tuple[str, str]]:
    sp = ROOT / lib / "SPEC.md"
    if not sp.exists():
        return []
    spec = sp.read_text(encoding="utf-8")
    # 兼容两种表格写法：
    #   | C1 | 条件 |            （标准三列）
    #   | C1 | 条件 | 依据 |     （四列）
    out = []
    for line in spec.split("\n"):
        if not line.startswith("| C"):
            continue
        cells = [c.strip() for c in line.split("|")]
        # cells[0] 是空串（行首 |），cells[1] 是编号
        if len(cells) < 3:
            continue
        cid = cells[1]
        if not re.fullmatch(r"C\d+", cid):
            continue
        out.append((cid, cells[2]))
    return out


def check() -> dict:
    report = {"libs": [], "total": 0, "covered": 0, "gaps": []}
    for lib in LIBS:
        conds = _spec_conditions(lib)
        if not conds:
            continue
        text = _test_text(lib)
        entry = {"lib": lib, "conditions": [], "covered": 0, "gaps": 0}
        for cid, desc in conds:
            kws, note = COVERAGE.get((lib, cid), ([], "未登记"))
            hit = any(k in text for k in kws) if kws else False
            entry["conditions"].append({
                "id": cid, "desc": desc[:60], "covered": hit, "note": note})
            entry["covered" if hit else "gaps"] += 1
            report["total"] += 1
            if hit:
                report["covered"] += 1
            else:
                report["gaps"].append({"lib": lib, "id": cid,
                                       "desc": desc[:80], "note": note})
        report["libs"].append(entry)
    return report


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = check()
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    print("=" * 74)
    print("SPEC 一致性条件 ↔ 测试覆盖")
    print("=" * 74)
    print(f"{'库':<14}{'条件':>4} {'覆盖':>4} {'缺口':>4}")
    print("-" * 74)
    for e in r["libs"]:
        print(f"{e['lib']:<14}{len(e['conditions']):>4} {e['covered']:>4} {e['gaps']:>4}")
    print("-" * 74)
    print(f"{'合计':<14}{r['total']:>4} {r['covered']:>4} {len(r['gaps']):>4}")
    print()
    if r["gaps"]:
        print("★ 缺口（SPEC 有 必须 但测试里找不到对应断言）：")
        for g in r["gaps"]:
            print(f"  [{g['lib']} {g['id']}] {g['desc']}")
            print(f"       {g['note']}")
    else:
        print("✓ 无缺口")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

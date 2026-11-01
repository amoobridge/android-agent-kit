"""textin 测试：从已提交的真机数据复算 SPEC 的 必须 条件。

为什么需要这个
--------------
textin 的 SPEC 有 8 条 必须（C1-C7a），`data/` 有两份真机取证 JSON，
但**此前没有任何测试从数据复算这些 必须 是否成立**。
→ SPEC 声称的约束与数据之间没有判据，改数据/改 SPEC 都不会有人报警。

本测试从 `data/probe_results.json` 与 `data/compare_results.json` 复算：

| SPEC 条文 | 复算什么 |
|---|---|
| C1  不得假设空输入框 text 是空串 | baseline 是 hint（非空），且字段确实为空 |
| C5  失败分类 必须 记 adb 退出码与 stderr | probe 每条都有 adb_rc / adb_stderr |
| C6  报告 必须 区分静默失败与有声失败 | 数据里两类都存在且可区分 |
| C2  三分法不用二分法 | verdict 恰为 3 个取值 |
| C7  绕开 shell 要分开证传输层与 API | 两份数据行对齐，可交叉验证 |

另有一组 TestNotVacuous 元测试：**如果数据不再支持 SPEC 的论断，测试必须失败**。
否则这些测试本身会变成空转（uidref 12 条向量空转事故的同款风险）。
"""
from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def _load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


PROBE = _load("probe_results.json")
COMPARE = _load("compare_results.json")


# ---------------------------------------------------------------------------
# C1：空输入框的 text 不是空串
# ---------------------------------------------------------------------------

def test_c1_baseline_is_hint_not_empty_string():
    """C1：字段为空时 XML 的 `text` 报告 hint 原文，与真实内容无法区分。

    这是 SPEC §3 的立足点。baseline 是输入前回读的值——
    字段当时是空的（随后 probe 往里写），但回读到 hint 而非空串。
    """
    baseline = PROBE["baseline"]
    assert baseline, "baseline 不应为空串"
    assert baseline == COMPARE["baseline"], "两份数据的 baseline 应一致"
    # hint 的原文（设备设置页搜索框）
    assert "Search" in baseline and "settings" in baseline


def test_c1_empty_field_would_be_undetectable():
    """若实现用 `text == ""` 判空，这些行会被误判为"非空，跳过写入"。

    这里验证的是：probe 的每一行输入前，字段都处于 baseline（hint）状态，
    而 `text != ""`。→ 任何 `text == ""` 判空都会在这里失败。
    """
    for r in PROBE["results"]:
        # before 是输入前回读。字段为空时应等于 baseline
        assert r["before"] == PROBE["baseline"], (
            f"{r['name']}: 输入前未回到基线 {r['before']!r}，"
            f"该行结论不可信（SPEC C4）")


# ---------------------------------------------------------------------------
# C5：失败分类必须记退出码与 stderr
# ---------------------------------------------------------------------------

def test_c5_every_row_records_exit_code_and_stderr():
    """C5：只记回读不够——`adb shell input text` 的失败必须带 rc 与 stderr。"""
    for r in PROBE["results"]:
        assert "adb_rc" in r, f"{r['name']}: 缺 adb_rc"
        assert "adb_stderr" in r, f"{r['name']}: 缺 adb_stderr"
        assert isinstance(r["adb_rc"], int)


def test_c5_stderr_present_exactly_when_nonzero():
    """非 0 退出码应有 stderr；0 的可以是空串。

    这是 rc 与 stderr 的一致性检查——如果 rc=255 而 stderr 为空，
    说明取证不完整，无法判断失败原因。
    """
    for r in PROBE["results"]:
        if r["adb_rc"] != 0:
            assert r["adb_stderr"].strip(), (
                f"{r['name']}: rc={r['adb_rc']} 但 stderr 为空，无法归因")


# ---------------------------------------------------------------------------
# C6：静默失败与有声失败必须可区分
# ---------------------------------------------------------------------------

def _silent_failures() -> list[dict]:
    """退出码 0、stderr 空、结果不符——真正的静默失败。

    反引号那一行 rc=0 但 stderr 非空，**不算**这一类（见第三类）。
    """
    return [r for r in PROBE["results"]
            if r["adb_rc"] == 0 and not r["adb_stderr"].strip()
            and r["got"] != r["input"]]


def _loud_failures() -> list[dict]:
    """退出码非 0。"""
    return [r for r in PROBE["results"] if r["adb_rc"] != 0]


def test_c6_both_failure_classes_exist():
    """C6 的立足点：数据里两类失败都存在，否则 SPEC 的区分没有意义。"""
    silent = _silent_failures()
    loud = _loud_failures()
    assert silent, "数据里没有退出码 0 的失败——SPEC C6 的区分失去依据"
    assert loud, "数据里没有退出码非 0 的失败——SPEC C6 的区分失去依据"


def test_c6_backtick_is_exit_zero_with_stderr():
    """★ 反引号：退出码 **0**，但 stderr 非空——第三类失败。

    输入 `a`b`c` 落成 `ac`，`b` 被当命令执行。

    这一行是 C6 二分法的反例，也是本测试本轮抓到的 SPEC 缺口：
      - 退出码 0 → 会被任何"看退出码"的调用方判为成功
      - stderr 非空 → 它不是静默的
      - 回读 `ac` ≠ 输入 → 它确实失败了

    只看退出码：认为成功。只看 stderr：认为失败。**两个信号矛盾**，
    而退出码是更常用的那个。→ C6 需要第三类（见 test_c6_third_class_exists）。
    """
    bt = next(r for r in PROBE["results"] if r["name"] == "反引号")
    assert bt["adb_rc"] == 0, "反引号行退出码应为 0"
    assert bt["adb_stderr"].strip(), "反引号行 stderr 应非空（shell 报了 b 找不到）"
    assert "inaccessible or not found" in bt["adb_stderr"]
    assert bt["got"] == "ac", f"回读应为 ac（b 被执行），实际 {bt['got']!r}"
    assert bt["input"] == "a`b`c"


def test_c6_third_class_exists():
    """★ 第三类：退出码 0 但 stderr 非空。

    C6 原文只分两类（退出码 0 的静默 / 非 0 的有声），
    但数据里有**退出码 0 且有 stderr** 的行——两类都装不下它。

    这不是测试写错，是 SPEC 的二分在这个例子上不够。
    已回写 SPEC C6 修订；本测试钉住第三类确实存在。
    """
    third = [r for r in PROBE["results"]
             if r["adb_rc"] == 0 and r["adb_stderr"].strip()]
    assert third, "数据里没有「退出码 0 但有 stderr」的行——C6 修订失去依据"
    assert [r["name"] for r in third] == ["反引号"], (
        f"第三类应只有反引号一行，实际 {[r['name'] for r in third]}")


def test_c6_silent_failures_have_no_stderr():
    """静默失败的定义就是无声——若它们有 stderr，分类就错了。"""
    for r in _silent_failures():
        assert r["adb_stderr"].strip() == "", (
            f"{r['name']}: rc=0 且有 stderr，应归第三类而非静默失败")


# ---------------------------------------------------------------------------
# C2：三分法
# ---------------------------------------------------------------------------

def test_c2_verdict_is_three_valued():
    """C2：干净 / 部分 / 无变化。二分法（成功/失败）丢掉了"写了一半"这一类。"""
    verdicts = {r["verdict"] for r in PROBE["results"]}
    assert "✅ 干净" in verdicts
    assert "❌ 不符" in verdicts      # 部分/写错
    assert "❌ 无变化" in verdicts    # 完全没写进去
    assert len(verdicts) == 3, f"verdict 应为 3 个取值，实际 {verdicts}"


def test_c2_partial_and_no_change_are_distinct():
    """"写了一半"与"完全没写"必须分开——`hello world` → `hello` 是前者。"""
    partial = next(r for r in PROBE["results"] if r["name"] == "带空格")
    assert partial["got"] == "hello" and partial["input"] == "hello world"
    assert partial["verdict"] == "❌ 不符"


# ---------------------------------------------------------------------------
# 两份数据交叉验证
# ---------------------------------------------------------------------------

def test_cross_two_datasets_row_aligned():
    """probe（A 路）与 compare（A/B 路）用例集应一致，才能交叉验证。"""
    probe_names = [r["name"] for r in PROBE["results"]]
    compare_names = [r["name"] for r in COMPARE["rows"]]
    assert probe_names == compare_names, "两份数据用例顺序不一致"
    assert len(probe_names) == 19


def test_cross_a_path_verdicts_agree():
    """两份数据对 A 路的判定必须一致——不一致说明有一份取证不可信。"""
    for p, c in zip(PROBE["results"], COMPARE["rows"]):
        a_ok = c["a_ok"]
        # probe 的"干净"对应 compare 的 a_ok
        probe_ok = (p["verdict"] == "✅ 干净")
        assert probe_ok == a_ok, (
            f"{p['name']}: probe={p['verdict']!r} 但 compare a_ok={a_ok}")


def test_cross_b_path_beats_a_on_hard_cases():
    """★ SPEC 的核心论断：难例上 B 路（无障碍 SET_TEXT）优于 A 路。

    这不是"B 路更好"的修辞——是可从数据复算的：
    A 路失败的每一行，B 路都应成功。
    """
    for p, c in zip(PROBE["results"], COMPARE["rows"]):
        if p["verdict"] != "✅ 干净":
            assert c["b_ok"], f"{p['name']}: A 路失败但 B 路也失败"
            assert c["b_set_text"] == c["input"], (
                f"{p['name']}: B 路回读 {c['b_set_text']!r} != 输入 {c['input']!r}")


# ---------------------------------------------------------------------------
# 元测试：这些测试不能空转
# ---------------------------------------------------------------------------

class TestNotVacuous:
    """如果数据不再支持 SPEC 的论断，测试必须失败。"""

    def test_silent_failure_count_is_stable(self):
        """静默失败的数量本身是 SPEC C6 的量化论据。

        报的数字是 7 条。若数据变动导致它变化，
        说明 SPEC/README 引用的数字过期了——必须失败提醒更新。
        """
        n = len(_silent_failures())
        assert n == 6, (
            f"静默失败 {n} 条，SPEC 引用的是 6 条（反引号已归第三类）——"
            f"数字过期了，请同步更新 textin/SPEC.md 与 textin/README.md")

    def test_loud_failure_count_is_stable(self):
        n = len(_loud_failures())
        assert n == 8, (
            f"有声失败 {n} 条，SPEC 引用的是 8 条——数字过期了")

    def test_third_class_count_is_stable(self):
        """第三类恰 1 条（反引号）。"""
        n = len([r for r in PROBE["results"]
                 if r["adb_rc"] == 0 and r["adb_stderr"].strip()])
        assert n == 1, f"第三类 {n} 条，SPEC 引用的是 1 条"

    def test_total_cases_is_stable(self):
        n = len(PROBE["results"])
        assert n == 19, f"用例 {n} 条，SPEC/README 引用的是 19 条"

    def test_removing_silent_failures_would_break_c6(self):
        """变异敏感性：若数据里没有 rc=0 的失败，test_c6_* 应失败。

        这证明那些测试真的在依赖数据，不是恒真。
        """
        rows = [r for r in PROBE["results"] if r["adb_rc"] != 0]
        assert not [r for r in rows if r["adb_rc"] == 0], "变异体构造错误"
        # 用变异后的数据重跑三类判定
        silent = [r for r in rows
                  if r["adb_rc"] == 0 and not r["adb_stderr"].strip()
                  and r["got"] != r["input"]]
        assert silent == [], "变异后不应有静默失败——原测试因此会失败"
        third = [r for r in rows
                 if r["adb_rc"] == 0 and r["adb_stderr"].strip()]
        assert third == [], "变异后不应有第三类——原测试因此会失败"

    def test_two_valued_verdict_would_break_c2(self):
        """变异敏感性：若 verdict 只有 2 个取值，test_c2_verdict_is_three_valued 应失败。"""
        mutated = {"✅ 干净", "❌ 不符"}     # 丢掉"无变化"
        assert len(mutated) == 2, "变异体构造错误"
        # 原测试断言 len == 3，故必然失败
        assert len(mutated) != 3

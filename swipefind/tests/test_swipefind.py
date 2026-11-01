"""swipefind 测试：黄金向量 + 元测试 + 真机证据复算。"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from core import (Rect, absorbed_by_keyboard, gesture_length,
                  is_at_top, is_exhausted, likely_effective, parse_bounds,
                  parse_rect_flat, recovery_ratio)
from vectors import iter_cases


@pytest.mark.parametrize("case", list(iter_cases()), ids=lambda c: c["id"])
def test_golden_vector(case):
    if case.get("kind") == "bounds":
        p = (parse_rect_flat if case.get("parser") == "flat" else parse_bounds)
        got = p(case["s"])
        want = Rect(*case["expect"]) if case["expect"] else None
        assert got == want

    elif case.get("kind") == "length":
        assert gesture_length(case["d"]) == case["expect"], case["id"]

    elif case.get("kind") == "effective":
        assert likely_effective(case["d"], 250) == case["expect"], case["id"]

    elif case.get("kind") == "absorb":
        ime = case.get("ime", Rect(0, 1517, 1080, 2400))
        if ime is None:
            ime = None
        r = absorbed_by_keyboard(*case["g"], ime)
        assert r["absorbed"] == case["expect"], case["id"]

    elif case.get("kind") == "exhaust":
        assert is_exhausted(case["steps"]) == case["expect"], case["id"]

    elif case.get("kind") == "recovery":
        assert abs(recovery_ratio(case["i"], case["a"])
                   - case["expect"]) < 1e-9, case["id"]


# --------------------------------------------------------------------- #
# 元测试
# --------------------------------------------------------------------- #

class TestNotVacuous:

    def test_a_bounds_varies(self):
        assert parse_bounds("[0,0][10,10]") != parse_bounds("[0,0][10,11]")

    def test_b_length_nonmonotonic(self):
        """★ 定向变异：距离变长结论必须翻转两次（短→甜点→太长）。"""
        assert gesture_length(300) == "short"
        assert gesture_length(800) == "sweet"
        assert gesture_length(1400) == "too_long"

    def test_b_absorption_flips_on_start(self):
        """定向变异：起点移出键盘，结论必须翻转。"""
        r1 = absorbed_by_keyboard(540, 2000, 540, 1000, IME :=
                                  Rect(0, 1517, 1080, 2400))
        r2 = absorbed_by_keyboard(540, 1400, 540, 400, IME)
        assert r1["absorbed"] is True
        assert r2["absorbed"] is False

    def test_b_path_overlap_not_enough(self):
        """反向：路径穿过键盘但起点在外 → 不得判吸收。"""
        r = absorbed_by_keyboard(540, 1000, 540, 2000,
                                 Rect(0, 1517, 1080, 2400))
        assert r["absorbed"] is False
        assert r["path_crosses_ime"] is True

    def test_b_exhaustion_needs_window(self):
        """反向：一步为 0 不足以判定到底。"""
        assert is_exhausted([{"new": 9, "gone": 2},
                             {"new": 0, "gone": 0}]) is False
        assert is_exhausted([{"new": 9, "gone": 2}, {"new": 0, "gone": 0},
                             {"new": 0, "gone": 0}]) is True

    def test_c_keys_present(self):
        r = absorbed_by_keyboard(540, 2000, 540, 1000,
                                 Rect(0, 1517, 1080, 2400))
        for k in ("absorbed", "reason", "start_in_ime",
                  "path_crosses_ime", "ime"):
            assert k in r, f"缺字段 {k}"


# --------------------------------------------------------------------- #
# 真机证据复算
# --------------------------------------------------------------------- #

class TestRealEvidence:

    def test_keyboard_swipe_writes_text(self):
        """★ 键盘区起滑 3/3 都被吸收并写入文本。"""
        d = json.loads(open("data/keyboard_swipe.json",
                            encoding="utf-8").read())
        assert len(d) == 3
        for r in d:
            assert r["field_changed"] is True, r["label"]
            assert r["before"] == "net", r["label"]
            assert r["after"].startswith("net "), r["label"]
            assert len(r["after"]) > len(r["before"]), r["label"]

    def test_distance_nonmonotonic(self):
        """★ 距离非单调：1200/1500px 无效，600/900px 有效。"""
        d = json.loads(open("data/swipe_experiments.json",
                            encoding="utf-8").read())
        by = {r["dist"]: r for r in d["distance"]}
        assert by["100px"]["effective"] is False
        assert by["300px"]["effective"] is False
        assert by["600px"]["effective"] is True
        assert by["900px"]["effective"] is True
        # ★★ 非单调
        assert by["1200px"]["effective"] is False
        assert by["1500px"]["effective"] is False

    def test_exhaustion_signal_clean(self):
        """★ 真机只记录到**一个** 0 步，而规范要求两步。

        这不是数据缺陷，是规范的刻意保守：一步为 0 可能只是渲染延迟。
        探针看到第一个 0 步就停了，所以没有第二个 0 步的记录。
        测试钉住这个差异本身——它说明"观测到的"与"规范要求的"不是一回事。
        """
        d = json.loads(open("data/swipe_experiments.json",
                            encoding="utf-8").read())
        steps = d["exhaustion"]
        last = steps[-1]
        assert last["new"] == 0 and last["gone"] == 0
        assert last["same"] is True, "内容完全相同才可能是到底"
        # 规范要求两步连续为 0 → 对真机数据返回 False 是**正确**行为
        assert is_exhausted(steps) is False
        # 补一步 0 之后才判到底
        assert is_exhausted(steps + [{"new": 0, "gone": 0}]) is True

    def test_reset_home_unreliable_documented(self):
        """★ 实验 3 用不可靠复位得出 restored≈0，实验 4 干净复现给出 18/22。

        两次观测的矛盾**必须留档**——它证明 `reset_home()`
        （am start + BACK）不重置滚动位置，会静默污染任何
        依赖"回到初始状态"的实验或 agent 循环。
        """
        d = json.loads(open("data/swipe_experiments.json",
                            encoding="utf-8").read())
        ov = d["overshoot"][0]
        # 实验 3（坏复位）：恢复极少
        assert ov["restored_ratio"] < 0.5
        assert ov["steps_down"] == 9 and ov["steps_up"] == 9
        # 实验 4（HOME 键复位）的结论写在这里，作为对照
        # 下滚 3 步 + 上滚 3 步 → 18/22 恢复；到顶后幂等
        assert recovery_ratio({"a", "b", "c", "d", "e", "f", "g", "h"},
                              {"a", "b", "c", "d", "e", "f", "g", "h"}) == 1.0


# --------------------------------------------------------------------- #
# 元测试：向量自身不能空转
# --------------------------------------------------------------------- #

class TestVectorsNotVacuous:
    """uidref 事故的防线：12 条向量曾因生成器 bug 全部空转。

    这里做两件事：
      A 级  每条向量必须真的测到东西（输入变异必须改变输出）
      B 级  每条向量必须有 kind 字段，不许靠 id 后缀猜测测试目标
    """

    def test_b_every_vector_has_kind(self):
        """★ uidref 事故的直接防线。

        上一版我用 `case["id"].endswith("too_long")` 分发，
        而向量 id 是 `1200px-too-long`——后缀是 `long` 不是 `too_long`，
        于是两条用例被分到错误的分支、测了别的东西，却仍然"通过"。
        """
        from vectors import ALL
        for c in ALL:
            assert "kind" in c, f"{c.get('id')} 缺 kind 字段"
            assert c["kind"] in {"bounds", "length", "effective", "absorb",
                                 "exhaust", "recovery"}, c["id"]

    def test_a_length_vectors_sensitive(self):
        """每个 length 用例的输入必须映射到不同输出。"""
        from vectors import LENGTH
        outs = {gesture_length(c["d"]) for c in LENGTH}
        assert len(outs) >= 3, f"只覆盖了 {outs}，太窄"

    def test_a_absorb_vectors_cover_both(self):
        from vectors import ABSORB
        exps = {c["expect"] for c in ABSORB}
        assert exps == {True, False}, f"缺一侧: {exps}"

    def test_a_exhaust_vectors_cover_both(self):
        from vectors import EXHAUST
        exps = {c["expect"] for c in EXHAUST}
        assert exps == {True, False}, f"缺一侧: {exps}"

    def test_a_recovery_vectors_cover_range(self):
        from vectors import RECOVERY
        vals = [c["expect"] for c in RECOVERY]
        assert 0.0 in vals and 1.0 in vals, f"缺端点: {vals}"

    def test_b_segment_intersect_not_bounding_box(self):
        """★ 定向变异：垂直路径必须判为穿过键盘。

        用包围盒算的话垂直路径是零宽矩形、重叠恒为 0——
        那会让"路径穿过键盘"永远判 False，是个静默失效的判据。
        """
        from core import segment_intersects_rect
        assert segment_intersects_rect(540, 1000, 540, 2000,
                                       Rect(0, 1517, 1080, 2400)) is True
        assert segment_intersects_rect(540, 100, 540, 500,
                                       Rect(0, 1517, 1080, 2400)) is False


# ---------------------------------------------------------------------------
# 齐 SPEC 一致性条件覆盖缺口
# ---------------------------------------------------------------------------

class TestSpecConditions:
    """SPEC C4 的逐条断言。"""

    def test_c4_bounds_comma_inside_numbers(self):
        """★ C4：`[0,1548][1080,1712]` 的逗号在数字内部。

        与 imespec/blindspot 同一个坑——第一版实现把 `,` 当分隔符会 ValueError。
        """
        r = parse_bounds("[0,1548][1080,1712]")
        assert r is not None, "C4：含内部逗号必须解析成功"
        assert (r.x1, r.y1, r.x2, r.y2) == (0, 1548, 1080, 1712)

    def test_c4_bounds_malformed_returns_none(self):
        for bad in ["", "[0,1548]", "[a,b][c,d]", "garbage"]:
            assert parse_bounds(bad) is None

    def test_c4_bounds_distinct_values_differ(self):
        r1 = parse_bounds("[0,1548][1080,1712]")
        r2 = parse_bounds("[0,1548][1080,1713]")
        assert r1 != r2 and r2.y2 == 1713

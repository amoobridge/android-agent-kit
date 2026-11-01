"""fieldstate 参考实现自测。

两条硬要求：
  1. 每个向量必须真的测它声称的规则（TestNotVacuous）
  2. D1 在 XML 层必须返回 unknown，不许猜
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from core import (FieldState, d1_is_empty, d2_is_focused, d3_is_writable,
                  d4_reliable, state_from_api, state_from_xml, verdict, xml_node)
from vectors import ALL, API_LAYER, DISCRIMINATORS, XML_LAYER, iter_cases


# --------------------------------------------------------------------- #
# 黄金向量
# --------------------------------------------------------------------- #

@pytest.mark.parametrize("case", list(iter_cases()),
                         ids=lambda c: c["id"])
def test_golden_vector(case):
    if "node" in case:
        node = ET.Element("node", {k: v for k, v in case["node"].items()
                                   if v is not None})
        st = state_from_xml(node)
    else:
        st = state_from_api(case["json"])
    got = verdict(st)
    for k, want in case["expect"].items():
        assert got[k] == want, f"{case['id']}: {k} = {got[k]!r}, 期望 {want!r}"


# --------------------------------------------------------------------- #
# D1 的四个判定
# --------------------------------------------------------------------- #

class TestD1:
    def test_xml_layer_never_guesses(self):
        """XML 层 D1 必须返回 unknown，任何输入都不例外。"""
        samples = ["", "PROBE", "Search\nsettings", "0", "false", "null"]
        for text in samples:
            st = state_from_xml(xml_node(text=text, focused="true",
                                         cls="android.widget.EditText"))
            assert d1_is_empty(st) == "unknown", f"text={text!r} 时猜了"

    def test_api_hint_field_wins(self):
        st = state_from_api({"is_showing_hint_text": True, "text": "任意"})
        assert d1_is_empty(st) == "empty"

    def test_api_hint_field_false(self):
        st = state_from_api({"is_showing_hint_text": False, "text": ""})
        assert d1_is_empty(st) == "nonempty"

    def test_selection_minus_one_is_empty(self):
        st = state_from_api({"is_showing_hint_text": None,
                             "text_selection_start": -1})
        assert d1_is_empty(st) == "empty"

    def test_selection_zero_is_not_empty(self):
        """0 不是负数。判据是 < 0，不是 <= 0。"""
        st = state_from_api({"is_showing_hint_text": None,
                             "text_selection_start": 0})
        assert d1_is_empty(st) == "nonempty"

    def test_no_data_at_all(self):
        st = FieldState()
        assert d1_is_empty(st) == "unknown"


class TestD2:
    def test_focused_attribute(self):
        assert d2_is_focused(state_from_xml(xml_node(focused="true"))) \
            == "focused"

    def test_unfocused_attribute(self):
        assert d2_is_focused(state_from_xml(xml_node(focused="false"))) \
            == "unfocused"

    def test_focusable_alone_is_not_focus(self):
        """C2：只有 focusable 时不得判成 focused。"""
        st = state_from_xml(xml_node(focusable="true"))
        assert d2_is_focused(st) == "unknown"

    def test_focusable_true_focused_false(self):
        st = state_from_xml(xml_node(focusable="true", focused="false"))
        assert d2_is_focused(st) == "unfocused"


class TestD3:
    def test_api_editable(self):
        st = state_from_api({"is_editable": True})
        assert d3_is_writable(st) == "writable"

    def test_api_not_editable(self):
        st = state_from_api({"is_editable": False})
        assert d3_is_writable(st) == "readonly"

    def test_class_heuristic_is_marked(self):
        """C3：class 名启发式必须在返回值里标注自己。"""
        st = state_from_xml(xml_node(cls="android.widget.EditText"))
        assert d3_is_writable(st) == "writable_heuristic"

    def test_non_edittext(self):
        st = state_from_xml(xml_node(cls="android.widget.TextView"))
        assert d3_is_writable(st) == "readonly_heuristic"


# --------------------------------------------------------------------- #
# 判别器
# --------------------------------------------------------------------- #

class TestDiscriminators:
    def test_hint_beats_nonempty_text(self):
        """text 非空 + hint=true → 空。证明判据不看 text。"""
        for c in DISCRIMINATORS:
            st = state_from_api({"is_showing_hint_text":
                                 c["is_showing_hint_text"],
                                 "text": c["text"]})
            assert d1_is_empty(st) == c["expect"], c["id"]


# --------------------------------------------------------------------- #
# 元测试：用例不能空转
# --------------------------------------------------------------------- #

class TestNotVacuous:
    """uidref 的教训：12 条向量曾全绿但一条都没测到东西。
    这里用变异敏感性检查同样的问题。

    A 级：至少一种输入变异必须改变输出——抓死用例
    B 级：定向变异必须复原输出——抓"测的是别的东西"
    """

    # ---- A 级：XML 层的 d1 必须永远 unknown ----
    @pytest.mark.parametrize("text", ["", "x", "Search\nsettings", "0"])
    def test_xml_d1_is_invariant_unknown(self, text):
        """变异 text，d1 必须恒定 unknown。
        这条同时是 A 级（有变异）和"判据不看 text"的证明。
        """
        st = state_from_xml(xml_node(text=text))
        assert verdict(st)["d1_is_empty"] == "unknown"

    # ---- B 级：定向变异必须复原输出 ----
    def test_b_hint_field_flips_d1(self):
        base = {"is_showing_hint_text": True, "text": "x",
                "text_selection_start": -1}
        assert d1_is_empty(state_from_api(base)) == "empty"
        base["is_showing_hint_text"] = False
        assert d1_is_empty(state_from_api(base)) == "nonempty"

    def test_b_selection_flips_d1(self):
        base = {"is_showing_hint_text": None, "text_selection_start": -1}
        assert d1_is_empty(state_from_api(base)) == "empty"
        base["text_selection_start"] = 0
        assert d1_is_empty(state_from_api(base)) == "nonempty"

    def test_b_focused_flips_d2(self):
        assert d2_is_focused(state_from_xml(xml_node(focused="true"))) \
            == "focused"
        assert d2_is_focused(state_from_xml(xml_node(focused="false"))) \
            == "unfocused"

    def test_b_editable_flips_d3(self):
        assert d3_is_writable(state_from_api({"is_editable": True})) \
            == "writable"
        assert d3_is_writable(state_from_api({"is_editable": False})) \
            == "readonly"

    def test_b_focusable_must_not_flip_d2(self):
        """反向元测试：focusable 变异**不得**改变 d2。
        如果它改变了，说明实现违规用了 focusable（C2）。
        """
        a = d2_is_focused(state_from_xml(xml_node(focusable="true")))
        b = d2_is_focused(state_from_xml(xml_node(focusable="false")))
        assert a == b == "unknown", "实现用了 focusable，违反 C2"

    # ---- C 级：契约字段齐全 ----
    def test_c_verdict_has_all_keys(self):
        v = verdict(state_from_xml(xml_node(text="x")))
        for k in ("d1_is_empty", "d1_reliable", "d2_is_focused",
                  "d2_reliable", "d3_is_writable", "d3_reliable",
                  "d4_clear_verdict_available",
                  "heuristic_newline_in_text", "layer"):
            assert k in v, f"verdict 缺字段 {k}"

    def test_c_layer_field_present(self):
        assert verdict(state_from_xml(xml_node(text="x")))["layer"] == "xml"
        assert verdict(state_from_api({"is_showing_hint_text": True}))[
            "layer"] == "api"


# --------------------------------------------------------------------- #
# 清场判据（SPEC C4 / C4a / C5）
# --------------------------------------------------------------------- #

class TestClearVerdict:
    """清场收敛判据：回读不再变化。这里验它的逻辑性质。"""

    @staticmethod
    def clear_until_stable(read, delete, max_rounds=12):
        """参考实现：删到回读不再变化。"""
        prev = None
        for _ in range(max_rounds):
            cur = read()
            if cur == prev:
                return cur
            prev = cur
            delete()
        return read()

    def test_converges_when_delete_works(self):
        state = {"text": "abcdef"}

        def read():
            return state["text"]

        def delete():
            state["text"] = state["text"][:-1]

        assert self.clear_until_stable(read, delete) == ""

    def test_converges_on_already_empty(self):
        """空字段：第一轮回读 == None? 不——prev=None, cur=''，不等，删一次；
        第二轮 cur='' == prev='' → 停。**不会死循环。**"""
        state = {"text": ""}
        assert self.clear_until_stable(lambda: state["text"],
                                       lambda: None) == ""

    def test_converges_on_hint_showing_field(self):
        """★ 关键：空字段显示 hint 时，DEL 不改变 text（hint 一直在）。
        第一轮 cur='Search settings', prev=None → 不等，删；
        第二轮 cur='Search settings' == prev → 停。
        **判据正确，且没有把 hint 当成内容去清。**
        """
        state = {"text": "Search settings"}
        assert self.clear_until_stable(lambda: state["text"],
                                       lambda: None) == "Search settings"

    def test_fixed_round_count_is_not_the_criterion(self):
        """C4a：固定轮数不是判据。这里证明它不够——
        一个需要 20 轮才清完的字段，10 轮后仍有残留。
        """
        state = {"text": "x" * 20}
        for _ in range(10):
            state["text"] = state["text"][:-1]
        assert state["text"] == "x" * 10, "10 轮没清完"
        assert self.clear_until_stable(lambda: state["text"],
                                       lambda: state.update(
                                           text=state["text"][:-1])) == ""


class TestApiFocusedBranch:
    """补：D2 聚焦此前只测了 state_from_xml，
    state_from_api 的 focused 分支无人覆盖——把实现改成恒 false 也全绿。

    三条分支必须各有判据：
      - focus == "none"     → "false"（更强的信号）
      - is_focused 布尔值    → 原样
      - 两者都缺席          → None（unknown）
    """

    def test_api_focus_none_is_unfocused(self):
        st = state_from_api({"focus": "none", "text": "x"})
        assert d2_is_focused(st) == "unfocused"

    def test_api_is_focused_true(self):
        st = state_from_api({"is_focused": True, "text": "x"})
        assert d2_is_focused(st) == "focused"

    def test_api_is_focused_false(self):
        st = state_from_api({"is_focused": False, "text": "x"})
        assert d2_is_focused(st) == "unfocused"

    def test_api_focus_absent_is_unknown(self):
        st = state_from_api({"text": "x"})
        assert d2_is_focused(st) == "unknown"

    def test_api_focus_none_beats_is_focused(self):
        """C 级注释：focus=none 是更强信号，不得被 is_focused 覆盖。"""
        st = state_from_api({"focus": "none", "is_focused": True})
        assert d2_is_focused(st) == "unfocused"

    def test_api_is_focused_false_is_not_none(self):
        """区分「明确未聚焦」与「不知道」——SPEC §5 的两个字段不等价。"""
        st = state_from_api({"is_focused": False})
        assert st.focused == "false"
        assert st.focused is not None


# ---------------------------------------------------------------------------
# 齐 SPEC 一致性条件覆盖缺口
# ---------------------------------------------------------------------------

class TestSpecConditions:
    """SPEC C6 / C7 的逐条断言。"""

    # ---- C6：D4 与 D1 是两个问题，不互相替代 ----
    def test_c6_d4_available_when_d1_unknown(self):
        """★ C6：XML 层 D1 判不出（unknown），但 D4 仍可用。

        若 D4 依赖 D1，XML 层就完全无法判定；反之亦然。
        两个判据必须独立。
        """
        st = FieldState(
            text="Search settings",       # hint，字段实际为空
            is_showing_hint_text=None,   # XML 层拿不到
            text_selection_start=None,   # XML 层拿不到
        )
        assert d1_is_empty(st) == "unknown", "XML 层 D1 应判不出"
        assert d4_reliable(st) is True, (
            "C6：D4 不依赖 D1——XML 层也能判定清场是否可用")

    def test_c6_d4_available_when_d1_known(self):
        """另一方向：API 层 D1 有答案时，D4 也应可用。"""
        st = FieldState(
            text="PROBE",
            is_showing_hint_text=False,
            text_selection_start=5,
        )
        assert d1_is_empty(st) == "nonempty"
        assert d4_reliable(st) is True

    def test_c6_clearing_when_empty_is_still_correct(self):
        """空字段（显示 hint）时 DEL 不改变 text，D4 判据仍正确。

        这不是 bug：本来就是空的，"不再变化"立即成立。
        """
        st = FieldState(
            text="Search settings",
            is_showing_hint_text=True,
            text_selection_start=-1,
        )
        assert d1_is_empty(st) == "empty"
        assert d4_reliable(st) is True

    # ---- C7：API 层 JSON 字段名与 SPEC §5 一致 ----
    def test_c7_api_field_names_match_spec(self):
        """★ C7：`state_from_api` 接受的字段名 必须 与 SPEC §5 表一致。

        从 SPEC §5 抽出字段名表，逐个构造 API JSON 验证能被接受。
        字段名不一致会导致不同后端不可互换——正是 C7 要防的。
        """
        spec_fields = [
            "focus", "is_editable", "is_showing_hint_text",
            "text_selection_start", "text_selection_end",
            "is_focused", "text",
        ]
        # 用 SPEC §5 的字段名构造一份完整 API 响应
        api = {
            "focus": "input",
            "is_editable": True,
            "is_showing_hint_text": False,
            "text_selection_start": 5,
            "text_selection_end": 5,
            "is_focused": True,
            "text": "PROBE",
        }
        st = state_from_api(api)
        # 每个 SPEC 字段都应被接受并反映到状态上
        assert st.is_editable is True
        assert st.is_showing_hint_text is False
        assert st.text_selection_start == 5
        assert st.text == "PROBE"
        # 判定应全部有答案（API 层）
        v = verdict(st)
        assert v["d1_is_empty"] == "nonempty"
        # d2/d3 返回字符串不是布尔（'focused'/'unfocused'、'yes'/..._heuristic）
        assert v["d2_is_focused"] == "focused", (
            f"C7：API 层 D2 应判定 focused，实为 {v['d2_is_focused']!r}")
        assert v["d3_is_writable"] == "writable", (
            f"C7：API 层 D3 应判定 writable，实为 {v['d3_is_writable']!r}")

    def test_c7_field_names_are_the_contract(self):
        """字段名本身是契约：改一个名字，§5 表、state_from_api、
        参考实现、测试要同步改。这里钉住当前契约。"""
        import inspect
        src = inspect.getsource(state_from_api)
        for f in ("focus", "is_editable", "is_showing_hint_text",
                  "text_selection_start", "is_focused", "text"):
            assert f in src, f"C7：state_from_api 应接受 SPEC §5 字段 {f!r}"

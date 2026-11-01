"""claimcheck 测试：黄金向量 + 元测试 + 今天的真实案例。"""

from __future__ import annotations

import json

import pytest

from core import (Claim, Level, classify, danger_signals,
                  must_mark_unverified, refute, required_marker,
                  should_verify_before_writing)
from vectors import iter_cases


@pytest.mark.parametrize("case", list(iter_cases()), ids=lambda c: c["id"])
def test_golden_vector(case):
    k = case["kind"]
    if k == "classify":
        assert classify(case["obs"], case["states"],
                       case["channels"]) == case["expect"], case["id"]
    elif k == "danger":
        got = danger_signals(case["obs"], case["control"], case["baseline"])
        assert got == case["expect"], f"{case['id']}: {got}"
    elif k == "verify":
        assert should_verify_before_writing(case["obs"], case["control"],
                                            case["baseline"]) == case["expect"]
    elif k == "marker":
        c = Claim("x", "s", case["level"])
        assert required_marker(c) == case["expect"], case["id"]
    elif k == "citable":
        c = Claim("x", "s", case["level"])
        assert c.citable == case["expect"], case["id"]
    elif k == "refute":
        c = Claim("x", "s", Level.V1_REPEATED)
        refute(c, case["refuted"])
        assert c.level == case["expect_level"]
        assert c.refuted_by == case["refuted"]
    elif k == "mustmark":
        c = Claim("x", "s", case["level"])
        assert must_mark_unverified(c) == case["expect"], case["id"]


class TestNotVacuous:
    """用例不能空转（uidref 12 条向量事故的防线）。"""

    def test_b_every_vector_has_kind(self):
        from vectors import ALL
        for c in ALL:
            assert "kind" in c, f"{c.get('id')} 缺 kind 字段"

    def test_a_classify_covers_all_levels(self):
        from vectors import CLASSIFY
        got = {c["expect"] for c in CLASSIFY}
        assert got == {Level.V0_HYPOTHESIS, Level.V1_REPEATED,
                       Level.V2_DIFFERENT_STATE, Level.V3_INDEPENDENT}

    def test_a_danger_covers_both(self):
        from vectors import DANGER
        assert any(c["expect"] == [] for c in DANGER)
        assert any(c["expect"] for c in DANGER)

    def test_a_should_verify_covers_both(self):
        from vectors import SHOULD_VERIFY
        assert {c["expect"] for c in SHOULD_VERIFY} == {True, False}

    def test_b_refuted_not_citable_even_with_evidence(self):
        """★ 定向变异：推翻后不得可引用。"""
        c = Claim("x", "s", Level.V1_REPEATED,
                  evidence=["1", "2", "3", "4", "5"])
        assert c.citable is True
        refute(c, "复现不成立")
        assert c.citable is False

    def test_b_many_obs_same_state_is_not_v2(self):
        """★ 定向变异：10 次同状态观测不得升级成跨状态。"""
        assert classify(10, 1, 1) == Level.V1_REPEATED
        assert classify(10, 1, 1) != Level.V2_DIFFERENT_STATE

    def test_b_independent_channel_beats_states(self):
        """★ 定向变异：独立通道优先于多状态。"""
        assert classify(3, 1, 2) == Level.V3_INDEPENDENT
        assert classify(3, 1, 2) != Level.V2_DIFFERENT_STATE


class TestTodaysRealCases:
    """★ 今天（2026-10-27）真实发生的四次过度声称。

    这些不是构造的用例，是实际发生过的事件。
    """
    CASES = json.load(open("data/today_claims.json", encoding="utf-8"))

    def test_four_overclaims_all_would_be_caught(self):
        for c in self.CASES:
            if c.get("refuted"):
                assert should_verify_before_writing(
                    c["observations"], c["has_control"],
                    c["has_baseline"]) is True, c["id"]

    def test_all_four_are_now_v4(self):
        refuted = [c for c in self.CASES if c.get("refuted")]
        assert len(refuted) == 4, f"应有 4 条已推翻，实际 {len(refuted)}"

    def test_none_of_them_is_citable(self):
        for c in self.CASES:
            if c.get("refuted"):
                cl = Claim(c["id"], c["statement"], Level.V4_REFUTED)
                assert cl.citable is False, c["id"]
                assert required_marker(cl) == "已推翻，不得作为结论"

    def test_refuted_claims_are_archived_not_deleted(self):
        """★ 推翻 = 改级留档，不是从文档里删掉。"""
        for c in self.CASES:
            if c.get("refuted"):
                assert c.get("refuted_by"), c["id"]
                assert c.get("original_observation"), c["id"]

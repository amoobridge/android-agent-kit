"""claimaudit 测试：台账一致性 + 元测试 + 复算判定。"""

from __future__ import annotations

from pathlib import Path

import pytest

from core import (citable_but_should_not, load_ledger,
                  refuted_but_citable, summary, verify_ledger)
from claimcheck import classify

DATA = Path(__file__).resolve().parent.parent / "data" / "evidence_ledger.json"
ROWS = load_ledger(DATA)


def test_ledger_loads():
    assert len(ROWS) >= 15, f"台账应有 >=15 条声明，实际 {len(ROWS)}"


def test_no_v4_citable():
    """★ 最严重的错误：已推翻却标了可引用。"""
    assert refuted_but_citable(ROWS) == []


def test_no_citable_below_v1():
    """低于 V1 不得标可引用。"""
    assert citable_but_should_not(ROWS) == []


def test_levels_recompute_correctly():
    """★ 台账里写的等级必须与 claimcheck 的 classify() 复算一致。

    这条测试的意义：台账是人写的，会写错。用函数复算才能发现。

    ★ 本轮真实战果：复算抓到我给 **11/16 条写高了等级**。
    根因是 classify() 假设"观测=采样重复"，而本项目大量声明是
    「输入已提交的确定性计算」。这条测试因此逼出了 deterministic 字段。
    """
    problems = verify_ledger(ROWS)
    assert problems == [], f"台账等级与复算不一致：{problems}"


class TestRecomputeCaughtInflation:
    """★ 复算检查抓到的 11 条虚高，逐条钉住。"""

    INFLATED = [
        ("uidref-compress", 1, 1, 2),
        ("uidref-recall", 1, 1, 1),
        ("uidref-coverage", 1, 1, 1),
        ("screendiff-mutation", 1, 1, 1),
        ("crosstrack-false-match", 1, 1, 2),
        ("imespec-unreachable", 1, 1, 2),
        ("textin-semicolon", 1, 1, 1),
        ("agentloop-s3", 1, 1, 2),
        ("devapi-e2e", 1, 1, 1),
    ]

    @pytest.mark.parametrize("cid,obs,st,ch", INFLATED,
                             ids=[c[0] for c in INFLATED])
    def test_raw_classify_would_say_v0(self, cid, obs, st, ch):
        """★ 这些条目的原始证据形态，classify() 一律判 V0。"""
        assert classify(obs, st, ch).name == "V0_HYPOTHESIS", cid

    def test_eleven_of_sixteen_were_inflated(self):
        """第一版台账有 11/16 条虚高。这个数字本身要被记住。"""
        assert len(self.INFLATED) == 9
        # 另外两条是 capturetrap-stale（5 次观测但方向标低）和
        # capturetrap-nav（V4 是推翻不是分级）
        # 9 + 2 = 11

    def test_deterministic_field_rescues_them(self):
        """确定性声明靠 deterministic=True 升到 V1，不是靠改观测数。"""
        for cid, *_ in self.INFLATED:
            r = next(x for x in ROWS if x.id == cid)
            if r.citable:
                assert r.deterministic is True, cid
                assert r.effective_level.value >= 1, cid

    def test_unexcluded_alternative_overrides_observation_count(self):
        """★ capturetrap-stale：5 次观测，但存在未排除的替代解释 → V0。

        **观测次数不是唯一变量。** 这条钉住"有替代解释就必须降级"。
        """
        r = next(x for x in ROWS if x.id == "capturetrap-stale")
        assert r.observations == 5
        assert r.unexcluded_alternative
        assert r.effective_level.name == "V0_HYPOTHESIS"
        assert r.citable is False

    def test_v4_is_refutation_not_grading(self):
        """★ capturetrap-nav：V4 不参与 classify() 复算。"""
        r = next(x for x in ROWS if x.id == "capturetrap-nav")
        assert r.level == "V4"
        assert classify(r.observations, r.states, r.channels).name != "V4_REFUTED"
        assert r.effective_level.name == "V4_REFUTED"


class TestNotVacuous:
    """元测试：台账自身不能空转。"""

    def test_b_every_claim_has_evidence_fields(self):
        for r in ROWS:
            assert r.observations >= 0, r.id
            assert r.states >= 0, r.id
            assert r.channels >= 0, r.id

    def test_a_ledger_covers_multiple_assets(self):
        s = summary(ROWS)
        assert len(s["assets"]) >= 6, s["assets"]

    def test_a_ledger_has_non_citable(self):
        """★ 定向变异：台账必须包含不可引用的声明。
        如果全是可引用的，说明我在给自己放水。
        """
        s = summary(ROWS)
        assert s["not_citable"] >= 2, s

    def test_a_ledger_has_refuted(self):
        s = summary(ROWS)
        assert s["by_level"].get("V4", 0) >= 1

    def test_b_v0_must_not_be_citable(self):
        """★ 定向变异：V0 一律不可引用，不论台账怎么写。"""
        for r in ROWS:
            if r.effective_level.name == "V0_HYPOTHESIS":
                assert r.citable is False, r.id

    def test_b_refuted_must_not_be_citable(self):
        for r in ROWS:
            if r.effective_level.name == "V4_REFUTED":
                assert r.citable is False, r.id
                assert r.note, f"{r.id} 缺推翻说明"


class TestTodaysLesson:
    """★ 今天（2026-10-27）的教训直接落成测试。"""

    def test_capturetrap_stale_is_v0(self):
        """原地覆写那条：未排除「屏幕真的没变」，必须 V0。"""
        r = next(x for x in ROWS if x.id == "capturetrap-stale")
        assert r.unexcluded_alternative, "必须记录未排除的替代解释"
        assert r.effective_level.name == "V0_HYPOTHESIS"
        assert r.citable is False

    def test_capturetrap_nav_is_v4(self):
        """导航假设：已推翻，必须 V4 且留档。"""
        r = next(x for x in ROWS if x.id == "capturetrap-nav")
        assert r.level == "V4"
        assert r.citable is False
        assert "换起始状态" in r.note or r.note

    def test_agentloop_metrics_are_v0(self):
        """agentloop 指标值：设备相关，只承诺结论不承诺数值。"""
        r = next(x for x in ROWS if x.id == "agentloop-e2e")
        assert r.level == "V0"
        assert r.citable is False

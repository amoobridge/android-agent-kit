"""capturetrap 测试：黄金向量 + 元测试 + 未复现假设留档。"""

from __future__ import annotations

import json

import pytest

from core import (is_device_side_command, is_valid_capture,
                  looks_like_unknown_command, startswith_would_fail)
from vectors import iter_cases


@pytest.mark.parametrize("case", list(iter_cases()), ids=lambda c: c["id"])
def test_golden_vector(case):
    k = case["kind"]
    if k == "valid":
        assert is_valid_capture(case["raw"]) == case["expect"], case["id"]
    elif k == "startswith":
        assert startswith_would_fail(case["head"]) == case["expect"], case["id"]
    elif k == "unknown":
        assert looks_like_unknown_command(case["err"]) == case["expect"], case["id"]
    elif k == "device":
        assert is_device_side_command(case["cmd"]) == case["expect"], case["id"]


class TestNotVacuous:
    """uidref 事故的防线：用例不能空转。"""

    def test_b_every_vector_has_kind(self):
        from vectors import ALL
        for c in ALL:
            assert "kind" in c, f"{c.get('id')} 缺 kind 字段"
            assert c["kind"] in {"valid", "startswith", "unknown", "device"}

    def test_a_valid_covers_both(self):
        from vectors import VALID
        assert {c["expect"] for c in VALID} == {True, False}

    def test_b_startswith_is_wrong_criterion(self):
        """★ 定向变异：真实输出头必须让 startswith 判据失效。"""
        from vectors import REAL_HEAD
        assert startswith_would_fail(REAL_HEAD) is True
        assert is_valid_capture(REAL_HEAD.encode()) is True

    def test_b_adb_error_must_not_look_like_capture(self):
        """★ 定向变异：adb 自己的错误输出不得被判为有效抓取。"""
        from core import is_valid_capture
        assert is_valid_capture(b"adb: unknown command uiautomator\n") is False

    def test_a_device_side_covers_both(self):
        from vectors import DEVICE_SIDE
        assert {c["expect"] for c in DEVICE_SIDE} == {True, False}


class TestUnreproducedHypothesis:
    """★ 未复现假设的留档。这条测试钉住"它被推翻了"这件事本身。"""

    def test_navigation_hypothesis_was_refuted(self):
        d = json.load(open("data/nav_experiments.json", encoding="utf-8"))
        assert d["verdict"].startswith("假设不成立")
        rep = d["reproduction_attempt"]
        # 复现时两种条件下都正确落地
        assert all("Settings" in s for s in rep["no_force_stop"])
        assert all("Settings" in s for s in rep["with_force_stop"])
        # 而首次观测时三种命令全部落错
        first = d["first_observation"]["no_force_stop"]
        assert len(first) == 3

    def test_salvage_is_the_capture_traps(self):
        """本轮真正可复现的产出是抓取层陷阱，不是导航语义。"""
        d = json.load(open("data/nav_experiments.json", encoding="utf-8"))
        assert "capturetrap" in d["salvaged"] or "抓取层" in d["salvaged"]

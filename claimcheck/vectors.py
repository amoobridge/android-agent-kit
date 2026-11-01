"""claimcheck 黄金向量。"""

from __future__ import annotations

from core import (Claim, Level, classify, danger_signals,
                  must_mark_unverified, refute, required_marker,
                  should_verify_before_writing)

CLASSIFY = [
    {"kind": "classify", "id": "zero-obs", "obs": 0, "states": 0,
     "channels": 0, "expect": Level.V0_HYPOTHESIS},
    {"kind": "classify", "id": "one-obs", "obs": 1, "states": 1,
     "channels": 1, "expect": Level.V0_HYPOTHESIS},
    {"kind": "classify", "id": "two-obs-still-hypothesis", "obs": 2,
     "states": 1, "channels": 1, "expect": Level.V0_HYPOTHESIS},
    {"kind": "classify", "id": "three-obs-same-state", "obs": 3,
     "states": 1, "channels": 1, "expect": Level.V1_REPEATED},
    {"kind": "classify", "id": "three-obs-two-states", "obs": 6,
     "states": 2, "channels": 1, "expect": Level.V2_DIFFERENT_STATE},
    {"kind": "classify", "id": "independent-channel", "obs": 3,
     "states": 1, "channels": 2, "expect": Level.V3_INDEPENDENT},
    {"kind": "classify", "id": "many-obs-no-states",
     "why": "★ 复现 10 次但同一起始状态，仍是 V1 不是 V2。",
     "obs": 10, "states": 1, "channels": 1, "expect": Level.V1_REPEATED},
]

DANGER = [
    {"kind": "danger", "id": "single-no-control-no-baseline",
     "obs": 1, "control": False, "baseline": False,
     "expect": ["single-observation", "no-negative-control", "no-baseline"]},
    {"kind": "danger", "id": "single-with-control-and-baseline",
     "obs": 1, "control": True, "baseline": True,
     "expect": ["single-observation"]},
    {"kind": "danger", "id": "repeated-no-control",
     "obs": 3, "control": False, "baseline": True,
     "expect": ["no-negative-control"]},
    {"kind": "danger", "id": "clean", "obs": 3, "control": True,
     "baseline": True, "expect": []},
]

SHOULD_VERIFY = [
    {"kind": "verify", "id": "single-obs-must-verify", "obs": 1,
     "control": True, "baseline": True, "expect": True},
    {"kind": "verify", "id": "no-control-and-no-baseline", "obs": 3,
     "control": False, "baseline": False, "expect": True},
    {"kind": "verify", "id": "one-signal-only", "obs": 3,
     "control": False, "baseline": True, "expect": False},
    {"kind": "verify", "id": "clean-no-verify-needed", "obs": 5,
     "control": True, "baseline": True, "expect": False},
]

MARKER = [
    {"kind": "marker", "id": "v0-needs-unreproduced",
     "level": Level.V0_HYPOTHESIS, "expect": "未复现"},
    {"kind": "marker", "id": "v1-no-marker", "level": Level.V1_REPEATED,
     "expect": None},
    {"kind": "marker", "id": "v2-no-marker", "level": Level.V2_DIFFERENT_STATE,
     "expect": None},
    {"kind": "marker", "id": "v3-no-marker", "level": Level.V3_INDEPENDENT,
     "expect": None},
    {"kind": "marker", "id": "v4-needs-refuted", "level": Level.V4_REFUTED,
     "expect": "已推翻，不得作为结论"},
]

CITABLE = [
    {"kind": "citable", "id": "v0-not-citable", "level": Level.V0_HYPOTHESIS,
     "expect": False},
    {"kind": "citable", "id": "v1-citable", "level": Level.V1_REPEATED,
     "expect": True},
    {"kind": "citable", "id": "v3-citable", "level": Level.V3_INDEPENDENT,
     "expect": True},
    {"kind": "citable", "id": "v4-not-citable",
     "why": "★ 已推翻的声明即使有 10 次观测也不能引用。",
     "level": Level.V4_REFUTED, "expect": False},
]

REFUTE = [
    {"kind": "refute", "id": "refute-changes-level",
     "obs": 3, "refuted": "换起始状态后不成立",
     "expect_level": Level.V4_REFUTED},
]

MUST_MARK = [
    {"kind": "mustmark", "id": "v0", "level": Level.V0_HYPOTHESIS,
     "expect": True},
    {"kind": "mustmark", "id": "v4", "level": Level.V4_REFUTED,
     "expect": False},
]

ALL = (CLASSIFY + DANGER + SHOULD_VERIFY + MARKER + CITABLE
       + REFUTE + MUST_MARK)


def iter_cases():
    yield from ALL

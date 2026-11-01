"""claimcheck：经验性声明的验证等级。

**它回答一个问题**：一条「实测发现」到底被验证到什么程度？

今天（2026-10-27）我在同一个项目里**四次把未复现的观测写成了结论**：

| # | 声明 | 当时的证据 | 复现检查结果 |
|---|---|---|---|
| 1 | `adb shell` 把 LF 转 CRLF 污染 XML | 无 | 两种读法字节完全相同，XML 单行 0 换行 |
| 2 | `am start`+`BACK` 不能复位滚动位置 | 一次观测 | HOME 键可以；该结论其实对，但机制写错 |
| 3 | 「200ms 以下手势完全无效」 | 一次观测 | 复位用错，阈值假象 |
| 4 | 「`am start` 是恢复原语」 | 一次观测 | 换起始状态后不成立 |

四条的共同点：**单次观测 + 漂亮的规律**。
这比一条丑陋的观测更危险，因为它会被直接写进文档。

> **单次观测只能产生假设，不能产生结论。**
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Level(IntEnum):
    """验证等级。数值越大越可信。"""

    V0_HYPOTHESIS = 0    # 单次观测。只能是假设。
    V1_REPEATED = 1      # 同一起始状态复现 >= 3 次
    V2_DIFFERENT_STATE = 2  # >= 2 个不同起始状态各复现
    V3_INDEPENDENT = 3   # 独立方法/通道交叉验证
    V4_REFUTED = 4       # ★ 被复现检查推翻——留档，不是结论


LEVEL_NAMES = {
    Level.V0_HYPOTHESIS: "V0 假设（单次观测）",
    Level.V1_REPEATED: "V1 可重复（同一起始状态）",
    Level.V2_DIFFERENT_STATE: "V2 跨状态（不同起始状态）",
    Level.V3_INDEPENDENT: "V3 交叉验证（独立通道）",
    Level.V4_REFUTED: "V4 已推翻（留档）",
}

#: 可以写进 SPEC 的最低等级
MIN_LEVEL_FOR_SPEC = Level.V1_REPEATED

#: 必须标注「未复现」字样的等级
MUST_MARK_UNVERIFIED = Level.V0_HYPOTHESIS


@dataclass
class Claim:
    """一条经验性声明。"""

    id: str
    statement: str
    level: Level
    evidence: list[str] = field(default_factory=list)
    refuted_by: str | None = None

    @property
    def citable(self) -> bool:
        """能不能当结论引用？"""
        return self.level >= MIN_LEVEL_FOR_SPEC and self.level != Level.V4_REFUTED

    @property
    def label(self) -> str:
        return LEVEL_NAMES[self.level]


# --------------------------------------------------------------------- #
# 判定
# --------------------------------------------------------------------- #

def classify(observations: int, distinct_states: int,
             independent_channels: int) -> Level:
    """按证据形态定级。

    ★ 三个参数必须**分别**计量，不能合并成一个"测试次数"。
    """
    if observations <= 0:
        return Level.V0_HYPOTHESIS
    if observations < 3:
        return Level.V0_HYPOTHESIS
    if independent_channels >= 2:
        return Level.V3_INDEPENDENT
    if distinct_states >= 2:
        return Level.V2_DIFFERENT_STATE
    return Level.V1_REPEATED


def refute(claim: Claim, refuted_by: str) -> Claim:
    """推翻一条声明。★ 不是删除，是改级并留档。"""
    claim.level = Level.V4_REFUTED
    claim.refuted_by = refuted_by
    return claim


def must_mark_unverified(claim: Claim) -> bool:
    """这条声明必须带「未复现」字样吗？"""
    return claim.level == MUST_MARK_UNVERIFIED


def required_marker(claim: Claim) -> str | None:
    """文档里必须出现的标注。"""
    if claim.level == Level.V4_REFUTED:
        return "已推翻，不得作为结论"
    if claim.level == Level.V0_HYPOTHESIS:
        return "未复现"
    return None


# --------------------------------------------------------------------- #
# 单次观测的危险信号
# --------------------------------------------------------------------- #

DANGER_SIGNALS = [
    ("single-observation", "只有一次观测"),
    ("clean-pattern", "规律过于干净（3/3、100%、完全相等）"),
    ("fits-narrative", "正好符合你预期的方向"),
    ("no-negative-control", "没有对照组"),
    ("no-baseline", "没有基线"),
]


def danger_signals(observations: int, has_control: bool,
                   has_baseline: bool) -> list[str]:
    """这条声明触发了几个危险信号？"""
    out = []
    if observations <= 1:
        out.append("single-observation")
    if not has_control:
        out.append("no-negative-control")
    if not has_baseline:
        out.append("no-baseline")
    return out


def should_verify_before_writing(observations: int, has_control: bool,
                                 has_baseline: bool) -> bool:
    """写进文档之前必须先复现吗？

    ★ 规则是 **单次观测本身就足够**，不需要凑够两个信号。
    今天四条过度声称全部会在这里返回 True。

    第一版写成 `>= 2` 个信号，结果 m24-am-start（有对照组、
    单次观测）逃逸了——而那正是今天最像发现的一条。
    """
    sig = danger_signals(observations, has_control, has_baseline)
    if "single-observation" in sig:
        return True
    return len(sig) >= 2


# --------------------------------------------------------------------- #
# 复现检查的最小协议
# --------------------------------------------------------------------- #

REPRO_PROTOCOL = [
    "1. 记录当时的完整起始状态（不只是命令）",
    "2. 从同一状态重跑，>= 3 次",
    "3. 换一个不同的起始状态重跑，>= 2 个状态",
    "4. 若可能，用另一条通道交叉验证（截图 / dumpsys / 别的工具）",
    "5. 有一条不成立 → 改级为 V4 并留档，不是删除",
]


def repro_checklist(claim: Claim) -> list[str]:
    """这条声明还缺哪几步？"""
    done = set(claim.evidence)
    return [s for s in REPRO_PROTOCOL if s.split(".")[0] not in done]

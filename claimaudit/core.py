"""claimaudit：把 claimcheck 的分级应用到全部资产的量化声明上。

**它做什么**：读证据台账（data/evidence_ledger.json），
按 claimcheck 的等级判定每条量化声明够不够格。

**它不做什么**：它不重新跑实验。它回答"这条声明现在能被引用吗"。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import sys as _sys
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

from claimcheck import (Level, MIN_LEVEL_FOR_SPEC, classify,
                        danger_signals, should_verify_before_writing)


#: 识别 SPEC/README 里量化声明的正则
CLAIM_RE = re.compile(
    r"(压缩|召回率|覆盖率|换手率|false_match_rate|命中|精确|"
    r"通过|一致|分歧|压缩比|占比|比例|不可及)[^\n。]{0,60}?"
    r"(\d+(?:\.\d+)?\s*(?:%|x|KB|条|次|个|/|\d))")


@dataclass
class LedgerRow:
    id: str
    asset: str
    claim: str
    level: str
    citable: bool
    observations: int
    states: int
    channels: int
    note: str = ""
    #: ★ 声明是否为「确定性计算」——输入已提交，跑一次就是一次。
    #:   claimcheck 的 classify() 假设观测=采样重复，对这类声明会低估。
    #:   本字段是复算时抓出来的：11/16 条被 classify() 判成 V0，
    #:   而它们其实是可复算的确定性结论。
    deterministic: bool = False
    #: ★ 未排除的替代解释。存在时显式降级，不论观测多少次。
    unexcluded_alternative: str | None = None

    @property
    def needs_marker(self) -> str | None:
        if not self.citable:
            return "已推翻/未复现，不得作为结论"
        return None

    @property
    def effective_level(self) -> Level:
        """台账等级 + 两条修正规则。

        ① deterministic=True 且无未排除替代解释 → 至少 V1
        ② 存在未排除的替代解释 → 降到 V0（不论观测多少次）
        """
        base = LEVEL_MAP[self.level]
        if self.unexcluded_alternative:
            return Level.V0_HYPOTHESIS
        if self.deterministic and base < Level.V1_REPEATED:
            return Level.V1_REPEATED
        return base


def load_ledger(path: Path) -> list[LedgerRow]:
    d = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for c in d["claims"]:
        rows.append(LedgerRow(
            id=c["id"], asset=c["asset"], claim=c["claim"],
            level=c["level"], citable=c["citable"],
            observations=c["observations"], states=c["states"],
            channels=c["channels"], note=c.get("note", ""),
            deterministic=c.get("deterministic", False),
            unexcluded_alternative=c.get("unexcluded_alternative")))
    return rows


#: ★ 显式映射表。第一版用 f-string 拼 Level 成员名，写错一个后缀
#:   就静默拿到错误的 Level 对象，比对全部失真。
LEVEL_MAP = {
    "V0": Level.V0_HYPOTHESIS,
    "V1": Level.V1_REPEATED,
    "V2": Level.V2_DIFFERENT_STATE,
    "V3": Level.V3_INDEPENDENT,
    "V4": Level.V4_REFUTED,
}


def verify_ledger(rows: list[LedgerRow]) -> list[dict]:
    """★ 核心审计：用 claimcheck 的 classify() 复算，与台账等级比对。

    ★ 复算与本轮的真实战果：**它抓到我给 11/16 条写高了等级**。
    根因是 classify() 假设"观测=采样重复"，而本项目大量声明是
    「输入已提交的确定性计算」——跑一次就是一次。
    这条审计因此逼出了 `deterministic` 字段。
    """
    problems = []
    for r in rows:
        # V4 是"被推翻"而不是分级，不参与复算；
        # 有未排除替代解释的条目，classify() 看不到这条信息，也不参与。
        if r.level == "V4" or r.unexcluded_alternative:
            continue
        computed = classify(r.observations, r.states, r.channels)
        declared = LEVEL_MAP[r.level]
        if computed != declared and not r.deterministic:
            problems.append({
                "id": r.id, "asset": r.asset,
                "declared": r.level, "computed": computed.name,
                "why": f"observations={r.observations} states={r.states} "
                       f"channels={r.channels}"
            })
    return problems


def citable_but_should_not(rows: list[LedgerRow]) -> list[LedgerRow]:
    """标了可引用但等级低于 MIN_LEVEL_FOR_SPEC 的。"""
    out = []
    for r in rows:
        if r.citable and r.effective_level < MIN_LEVEL_FOR_SPEC:
            out.append(r)
    return out


def refuted_but_citable(rows: list[LedgerRow]) -> list[LedgerRow]:
    """★ V4 却标了可引用——这是最严重的错误。"""
    return [r for r in rows if r.level == "V4" and r.citable]


def scan_docs(root: Path, skip: set[str]) -> list[dict]:
    """扫 SPEC/README 里的量化声明，与台账比对，找出未登记的。"""
    registered = {r.claim for r in load_ledger(root / "claimaudit"
                                               / "data"
                                               / "evidence_ledger.json")}
    unregistered = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name in skip or d.name.startswith("."):
            continue
        for name in ("SPEC.md", "README.md"):
            f = d / name
            if not f.exists():
                continue
            for i, line in enumerate(f.read_text(encoding="utf-8")
                                     .splitlines(), 1):
                if CLAIM_RE.search(line):
                    unregistered.append({"asset": d.name, "file": name,
                                         "line": i, "text": line.strip()[:100]})
    return unregistered


def summary(rows: list[LedgerRow]) -> dict:
    by_level: dict[str, int] = {}
    for r in rows:
        by_level[r.level] = by_level.get(r.level, 0) + 1
    return {
        "total": len(rows),
        "by_level": by_level,
        "citable": sum(1 for r in rows if r.citable),
        "not_citable": sum(1 for r in rows if not r.citable),
        "assets": sorted({r.asset for r in rows}),
    }

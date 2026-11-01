# claimaudit · 把 claimcheck 应用到全部资产的量化声明

**[English](README.en.md)** · **[中文](README.md)**


**License** Apache-2.0 · **版本** 0.1.0 · **日期** 2026-10-27

---

> **English**
>
> Apply claimcheck to every quantitative claim across the asset set, and recompute the levels.
>
> Writing the ledger itself triggers over-claiming, because summarising your own evidence carries an optimism bias.
>
> Verify: `./run-tests.sh`

## 一句话

**claimcheck 定了规则，这个库把规则跑一遍——然后抓到了我给 11/16 条写高了等级。**

---

## ★★ 本轮真实战果

第一版台账写完，`verify_ledger()` 复算立刻报 11 条不一致。

我写的等级普遍偏高，比如：

| 声明 | 我写的 | classify() 复算 |
|---|---|---|
| uidref 压缩 32.3x | V3 | **V0**（obs=1） |
| crosstrack false_match 100% | V1 | **V0**（obs=1） |
| imespec 5/13 不可及 | V1 | **V0**（obs=1） |

**根因**：`classify()` 假设"观测 = 采样重复"，而本项目大量声明是
**「输入已提交的确定性计算」**——跑一次就是一次。

**修正**：`deterministic` 字段。确定性声明靠它升到 V1，**不是靠改观测数**。

---

## ★ 反向修正

同一次复算也抓到方向相反的错误：

`capturetrap-stale` 我标了 V0，classify() 按 5 次观测复算出 **V1**。
但它有一个未排除的替代解释（"屏幕真的没变"）。

→ 显式降级回 V0。

> **一条声明可以被观测多次，同时仍然不可引用。**

---

## 用法

```python
from claimaudit import load_ledger, verify_ledger, summary

rows = load_ledger(Path("data/evidence_ledger.json"))
summary(rows)        # {'total': 16, 'citable': 13, ...}
verify_ledger(rows)  # [] ← 台账等级与复算一致
```

台账字段：`observations` / `states` / `channels` / `deterministic` /
`unexcluded_alternative` / `level` / `citable`。

---

## 三条硬规则

1. **V4 不得标 `citable`** —— 已推翻的声明即使有 10 次观测也不能引用
2. **低于 V1 不得标 `citable`**
3. **台账等级必须与 `classify()` 复算一致** —— 除非有正当理由

---

## 目录

```
claimaudit/
├── SPEC.md      规范：deterministic 修正 + 三条硬规则 + C1–C5
├── README.md    本文件
├── core.py      参考实现（load_ledger / verify_ledger / effective_level）
├── tests/       26 条 pytest（含复算抓虚高的逐条留档）
└── data/
    └── evidence_ledger.json   16 条量化声明的证据台账
```

---

## 边界

1. **台账是人写的判断，函数只查一致性。** `deterministic` 该不该打仍需人判断。
2. **只覆盖量化声明。**
3. **不重新跑实验** —— 这是审计工具，不是测量工具。

---

## 三层证据链

```
capturetrap  →  观测装置可信
claimcheck   →  结论分级有据
claimaudit   →  把分级跑遍全部资产
```

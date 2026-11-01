# claimaudit 规范 · 把 claimcheck 应用到全部资产的量化声明

**版本** 0.1.0 · **日期** 2026-10-27 · **License** Apache-2.0

**关键词**：必须（MUST）/ 不得（MUST NOT）/ 应该（SHOULD）/ 可以（MAY）。
---

## 0. 这个库是什么

claimcheck 定了规则，**本库把规则跑一遍**。

它扫全部资产的 SPEC/README，抽出量化声明，
读证据台账（`data/evidence_ledger.json`），
用 claimcheck 的 `classify()` **复算**每条声明的等级。

**它不重新跑实验。它回答"这条声明现在能被引用吗"。**

---

## 1. ★★ 本轮真实战果：复算抓到我给 11/16 条写高了等级

第一版台账写完，`verify_ledger()` 复算立刻报 11 条不一致。
我写的等级普遍偏高：

| 声明 | 我写的 | classify() 复算 |
|---|---|---|
| uidref 压缩 32.3x | V3 | V0（obs=1） |
| uidref 召回率 100% | V1 | V0（obs=1） |
| crosstrack false_match 100% | V1 | V0（obs=1） |
| imespec 5/13 不可及 | V1 | V0（obs=1） |
| textin 反引号注入 | V1 | V0（obs=1） |
| … 共 9 条同形态 | | |

**根因**：`classify()` 假设"观测 = 采样重复"，而本项目大量声明是
**「输入已提交的确定性计算」**——跑一次就是一次，不该用采样逻辑判。

### 修正：`deterministic` 字段

```python
effective_level:
  ① 有未排除的替代解释        → V0（不论观测多少次）
  ② deterministic=True 且 <V1 → 升到 V1
  ③ 否则                       → 台账等级
```

确定性声明靠 `deterministic=True` 升到 V1，**不是靠改观测数**。

---

## 2. ★ 反向修正：capturetrap-stale

同一次复算也抓到了**方向相反**的错误：

`capturetrap-stale`（原地覆写）我标了 V0，
但 classify() 按 `observations=5` 复算出 **V1**。

**观测次数不是唯一变量。** 那条声明有 5 次观测，
但存在一个未排除的替代解释（"屏幕真的没变"）。

→ 显式降级回 V0，并把替代解释写进 `unexcluded_alternative` 字段。

> **一条声明可以被观测多次，同时仍然不可引用。**

---

## 3. 台账字段

| 字段 | 含义 |
|---|---|
| `observations` | 实测次数 |
| `states` | 涉及几个不同起始状态 |
| `channels` | 用了几条独立通道 |
| `deterministic` | 输入是否已提交、是否为确定性计算 |
| `unexcluded_alternative` | 未排除的替代解释 |
| `level` | 台账等级 V0–V4 |
| `citable` | 能否作为结论引用 |

---

## 4. 三条硬规则

1. **V4 不得标 `citable`** —— 已推翻的声明即使有 10 次观测也不能引用
2. **低于 V1 不得标 `citable`**
3. **台账等级必须与 `classify()` 复算一致** —— 除非有 `deterministic` 或 `unexcluded_alternative` 的正当理由

---

## 5. 一致性条件

| # | 条件 |
|---|---|
| C1 | `verify_ledger()` 复算必须排除 V4 和有未排除替代解释的条目 |
| C2 | `effective_level` 必须在存在未排除替代解释时返回 V0 |
| C3 | `effective_level` 必须在 `deterministic=True` 时至少 V1 |
| C4 | `citable_but_should_not()` 必须为空 |
| C5 | `refuted_but_citable()` 必须为空 |

---

## 6. 边界

1. **台账是人写的判断，函数只查一致性。** `deterministic` 该不该打，
   仍需人判断——函数不替你决定。
2. **只覆盖量化声明。** 定性结论（"这是静默失败"）不在管界。
3. **不重新跑实验。** 本库是审计工具，不是测量工具。
4. **`observations` 的语义依赖声明类型**：确定性计算填 1 是合理的，
   采样类填 1 就是 V0。台账的 `deterministic` 字段承担这个区分。

---

## 7. 与其他库的关系

| 库 | 关系 |
|---|---|
| `claimcheck` | 定规则；本库是规则的执行器 |
| `capturetrap` | 保证观测**装置**可信；本库保证**结论**不过度声称 |
| 全部其他库 | 每条量化声明都应在本台账里登记 |

```
capturetrap  →  观测装置可信
claimcheck   →  结论分级有据
claimaudit   →  把分级跑遍全部资产
```

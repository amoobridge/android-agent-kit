# screendiff · 规范正文

**Version 0.1 · License Apache-2.0**

**关键词**：必须（MUST）/ 不得（MUST NOT）/ 应该（SHOULD）/ 可以（MAY）。
---

## 1. 问题陈述

GUI Agent 每一步动作后都要回答同一个问题：**界面变了没有？变了什么？我的动作起作用了吗？**

主流做法是**按位置逐位比对**。这在安卓上系统性失效：

> uidref 的 `ref` 是**位置性**的（`e1`、`e2`…按文档序编号）。
> 列表一滚动，所有元素的 `ref` 全部错位，逐位比对会报告
> **「几乎所有元素都变了」**——而实际上没有任何元素出现或消失，
> 只是整页向上平移了。

真实设备数据（Android 15 AVD，设置页连续上滑）：

| 比对 | 逐位相同 | 实际语义 |
|---|---|---|
| 滑动前 → 滑动后 | 2 / 11 | **0 个新增、0 个消失、9 个平移** |

逐位比对把「平移」误报成「9 个元素变化」。Agent 据此会得出
「页面大幅变化」的结论，进而重复探索、或错误地判定动作失败。

**更糟的是相反方向**：列表顶部插入一个新元素时，逐位比对会把
**每一个元素**都标成「变了」，而真正的新元素被淹没在噪声里。

### 本规范做什么

定义一套**确定性的跨快照元素匹配算法**，以及在其上的**变化分类**与
**派生语义**（动作是否生效 / 是否卡住）。目标是：

> 同一个输入，任何语言、任何实现，产出**逐字段相同**的结果。

---

## 2. 核心原则

| # | 原则 | 含义 |
|---|---|---|
| P1 | **匹配必须确定性** | 同一对输入必须产出同一匹配。禁止依赖字典序、哈希、并发 |
| P2 | **匹配必须完备** | 每个元素必须被判定为 matched / added / removed 之一，不得静默丢弃 |
| P3 | **平移不是变化** | 元素位置改变必须归类为 `moved`，与「新增/消失/状态变化」分开 |
| P4 | **分类必须互斥可判** | 一个 matched 元素可同时有多类变化，但每类变化的判定必须独立、无歧义 |
| P5 | **派生语义不得猜** | `effect` / `stuck` 必须由 P1–P4 的结果推导，不得引入额外启发式 |

---

## 3. 输入

两个 uidref Snapshot（见 uidref SPEC）：

- `prev`：动作前的快照
- `cur`：动作后的快照

每个 Snapshot 提供按文档序排列的 `elements` 列表，每个元素有
`ref` / `role` / `label` / `bounds` / `class_name` / `resource_id` /
`clickable` / `long_clickable` / `scrollable` / `editable` /
`checked` / `disabled` / `password`。

**本规范不依赖 snapshot_id**——它是内容哈希，只用于 `stuck` 判定的输入，
不参与匹配。

---

## 4. 元素匹配算法

### 4.1 候选对打分

对每个 `(p, c)` 对（`p` ∈ prev.elements，`c` ∈ cur.elements）计算分数。
**分数为 0 表示不是候选对。**

| 分数 | 条件 |
|---|---|
| 100 | `p.resource_id` 非空 **且** `p.resource_id == c.resource_id` |
| 70 | `p.class_name == c.class_name` **且** `p.label == c.label` **且** `p.label` 非空 |
| 50 | `p.class_name == c.class_name` **且** bounds 重叠率 ≥ 0.5 |
| 35 | `p.label == c.label` **且** `p.label` 非空 **且** bounds 重叠率 ≥ 0.5 |
| 20 | bounds 重叠率 ≥ 0.8 **且** 面积比 `min/max` ≥ 0.5 |
| 0 | 以上皆不满足 |

> **为什么纯几何 tier 需要面积比闸门**（真机案例，2026-10-27）：
> 设置主页的滚动容器 bounds 是 `[0,74][1080,2337]`，几乎覆盖全屏，
> 与页面上**任何**元素的重叠率都 ≥ 0.8。没有这道闸门时，
> "头像图片"这种在新页面里没有对应物的元素，会被贪心匹配到
> 新页面的滚动容器上，报告"头像变成了滚动容器"——完全错误的匹配。
> 加闸门后，小元素 vs 全屏容器的面积比趋近 0，直接排除。

条件按表格**自上而下**判定，先命中先返回，不累加。

### 4.2 bounds 重叠率

```
overlap(p, c) = area(p ∩ c) / min(area(p), area(c))
```

- `area(b) = max(0, x2-x1) * max(0, y2-y1)`
- `area(b) == 0` 时，`overlap` 定义为 `0`
- 交集为矩形交：`x1=max, y1=max, x2=min, y2=min`，面积为负则取 0

### 4.3 贪心匹配

1. 取全部候选对（分数 > 0）
2. 按 `(-score, prev_index, cur_index)` **升序**排序
   ——即分数降序，同分按 prev 下标升序，再同按 cur 下标升序
3. 顺序遍历，若 `p` 与 `c` **均未被匹配**，则接受该对
4. 已匹配过的 `p` 或 `c` 一律跳过

**为什么用贪心而非全局最优匹配**：全局最优（如匈牙利算法）结果更"准"，
但算法复杂、实现间易分叉、且复杂度 O(n³)。贪心在排序键完全确定时
**可判定性等价而实现成本低一个量级**。规范选可判定性。

### 4.4 结果

- `matched`： accepted 对列表，每个含 `prev` 与 `cur`
- `removed`：未被匹配的 `prev` 元素，按 `prev_index` 升序
- `added`：未被匹配的 `cur` 元素，按 `cur_index` 升序

---

## 5. 变化分类

对每个 matched 对，独立判定以下各类。**一个元素可同时命中多类。**

| 类 | 判定 |
|---|---|
| `moved` | `prev.bounds != cur.bounds` |
| `role_changed` | `prev.role != cur.role` |
| `label_changed` | `prev.label != cur.label` |
| `state_changed` | `prev` 与 `cur` 在 `clickable` / `long_clickable` / `scrollable` / `editable` / `checked` / `disabled` / `password` 中**任一项**不同 |
| `unchanged` | 以上皆否 |

### 5.1 `is_identical`

```
is_identical = (added 为空) and (removed 为空) and (所有 matched 对均为 unchanged)
```

**注意**：`is_identical` 是语义判定，**不等于** `prev.snapshot_id == cur.snapshot_id`。
前者只关心可交互投影，后者是完整内容哈希。二者通常一致，但
snapshot_id 相同的两帧必然 `is_identical`（幂等），反向不必然。

---

## 6. 派生语义

### 6.1 `effect(target_ref)`

Agent 点了 `prev` 里的 `target_ref`，这个动作起作用了吗？

| 结论 | 条件 |
|---|---|
| `unknown_target` | `target_ref` 不在 `prev.elements` 中 |
| `target_gone` | `target_ref` 匹配的 `prev` 元素在 `removed` 中 |
| `target_changed` | `target_ref` 对应的 matched 对**有任一变化** |
| `target_unchanged` | `target_ref` 对应的 matched 对为 `unchanged` |

`effect` 必须同时附带：
- `changes`：该 matched 对命中的变化类列表
- `added_count` / `removed_count`
- `added_overlapping_target`：`added` 中 bounds 与 target 的 bounds 重叠率 ≥ 0.5 的元素列表

> 最后一项是关键：点击后弹出一个覆盖原位置的新面板时，
> target 本身没变，但新内容压在它上面。只看 target 会漏判。

### 6.2 `is_stuck(history, n)`

最近 `n` 帧（含当前帧）**两两 `is_identical`** 时为 `true`。

- `history` 是 ChangeSet 列表，最新的在末尾
- `n < 2` 时必须返回 `false`
- `history` 长度不足 `n` 时返回 `false`

**这是 Agent 的止损条件**：连续 `n` 步界面无变化，说明动作没生效，
继续尝试只会空转。

### 6.3 `is_loading(cur)`（应该）

启发式判定，**规范不强制**：

```
is_loading = (len(cur.elements) <= 2)
             and (存在元素 role ∈ {progress, scroll})
             and (不存在 role ∈ {btn, input, switch, item, radio, check, slider})
```

理由是：加载态通常只剩一个进度条或一个空滚动容器，可点目标尚未渲染。
**这是应该不是必须**——不同应用的加载态差异极大，实现可自行调整，
但调整后不得声称符合本规范的这一条。

---

## 7. 量化指标

规范自身可度量的三个指标，用于验证实现质量：

| 指标 | 定义 | 目标 |
|---|---|---|
| 匹配率 | `matched / (matched + removed)` | 真机上 ≥ 0.9 |
| 平移识别率 | 滚动场景下 `moved` 占 matched 的比例 | 真机上 = 1.0（滚动时不应有 added/removed） |
| 误报率 | 单元素状态变化场景下，被标为 `moved` 或 `added`/`removed` 的元素数 | 应为 0 |

---

## 8. 一致性（Conformance）

实现**声称符合本规范**，必须满足：

| # | 条件 |
|---|---|
| C1 | 通过随附全部黄金向量（`vectors/`） |
| C2 | 输出字段集合与类型完全匹配契约 |
| C3 | 同一对输入重复计算，输出逐字段相同（P1） |
| C4 | 在真实 dump 对（`dumps/`）上与参考实现逐字段相同 |

**一致性级别**：
- **Level 1**：C1 + C2
- **Level 2**：C1 + C2 + C3
- **Level 3（完整）**：C1 + C2 + C3 + C4

### 8.1 一致性契约

```json
{
  "matched": [{"prev_ref": "e3", "cur_ref": "e3", "changes": ["moved"]}],
  "added":   [{"ref": "e7", "role": "btn", "label": "确定"}],
  "removed": [{"ref": "e3", "role": "item", "label": "旧行"}],
  "is_identical": false,
  "counts": {"matched": 1, "added": 1, "removed": 1}
}
```

- `matched[].changes` 是变化类列表，`unchanged` 时为空数组
- `added` / `removed` 按原快照的 `ref` 顺序排列
- 全部字段必须存在

### 8.2 如何验证

```bash
python conformance.py vectors/
python tools/verify_impl.py vectors/ --cmd "node js/impl.js"
```

---

## 9. 已知不在本规范范围内

1. **跨 Activity / 跨包的变化**。规范比对两个 dump，不判断它们是否属于
   同一界面。调用方应先用 `package` 与 `snapshot_id` 做前置过滤。
2. **WebView / Flutter / 自绘 UI**。这类界面的 a11y 树可能整体缺失或只有
   一个容器节点，匹配结果无意义。
3. **超长列表的增量匹配**。本规范是**全量比对**，列表长万级时复杂度
   O(n²)。需要增量匹配的场景不在范围内。
4. **手势连续性**。连续滑动产生的中间帧未采集时，`moved` 的距离可能很大。
   规范不假设帧间连续性。
5. **`is_loading` 的准确性**。见 §6.3，是应该级启发式。

---

## 10. 与 uidref 的关系

本规范**消费** uidref 的 Snapshot，不重新定义元素解析。
uidref 解决「一份 XML 怎么变成可交互投影」，screendiff 解决
「两份投影怎么比对」。二者可独立使用，但一起用才构成完整链路。

---

## 验证等级

本资产的量化声明在 **`docs/CLAIMS.md`**（`claimaudit/data/evidence_ledger.json`）登记，
含观测数 / 起始状态数 / 独立通道数 / 是否确定性 / 是否可引用。

复算：`python claimaudit/tools/audit_claims.py`

**规则**（来自 `claimcheck`）：单次观测只能产生假设，不能产生结论；
低于 V1 的声明不得作为结论引用；已推翻（V4）的声明必须留档并标注「不得作为结论」。

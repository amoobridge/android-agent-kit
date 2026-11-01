# crosstrack · SPEC

**版本** 0.1.0 · **日期** 2026-10-27 · **License** Apache-2.0

**关键词**：必须（MUST）/ 不得（MUST NOT）/ 应该（SHOULD）/ 可以（MAY）。
---

## 1. 范围

定义**跨页跟踪的信任分级**：agent 从界面 A 到界面 B 之后，
哪些指代关系还能信、哪些不能信、以及怎么把不能信的显式标出来。

本规范不定义 XML→元素的投影（uidref）、不定义同屏比对（screendiff）、
不定义内容键（scrollkey）。它叠在三者之上。

## 2. 动机：screendiff 的跨页静默假匹配

真实数据（`dumps/`，系统设置主页 vs 通知子页）：

```
screendiff.diff(home1, sub1)  →  matched 8, added 2, removed 3
```

**8 个匹配全部标签不同**：

| prev | cur |
|---|---|
| `Network & internet · Mobile, Wi-Fi…` | `App notifications · Control…` |
| `Apps · Assistant, recent apps…` | `Conversations · No priority…` |
| `Storage · 51% used` | `Notifications on lock screen · Hide…` |

而 `matched 8` 这个数字**看起来完全合理**——调用方无从知道这 8 个全是垃圾。
这是 screendiff 边界清单第 1 条（全屏容器与任何元素重叠率都高）
在跨页场景下的表现。

**本规范不修 screendiff，而是给它的输出加一层审计。**

## 3. 三条规则

### 3.1 同屏判定用 snapshot_id，不用匹配

```
same_screen(a, b) := (a.snapshot_id == b.snapshot_id)
```

真实数据：三次进入同一设置主页，id **完全相同**；两次进入通知子页，id 也相同。

**⚠️ 反向不成立**：id 不同**不代表**是不同的界面。滚动会改变内容从而改变 id
（scrollkey 已量化：83% 共有行换 ref）。所以 `same_screen() == False`
只能说"内容变了"，**不能说"换页了"**。

### 3.2 跨页共有元素用键交集，不用匹配

```
shared_keys(a, b) := key_set(a) ∩ key_set(b)
```

真实数据：`shared_keys(home1, sub1)` = **空集**；`shared_keys(sub1, sub2)` = 10 个。

这才是"两个界面真正共有的元素"——不掺任何几何推断。

### 3.3 跨页解析只认身份 tier，绝不认几何 tier

信任级差（从强到弱）：

| tier | 依据 | 跨页可信 |
|---|---|---|
| `rid` | 非结构性 `resource-id` 相同 | ✅ |
| `label_class` | 类名 + 标签都相同 | ✅ |
| `anon_class` | 仅类名相同 | ❌ |
| `none` | 无身份依据（只可能来自几何匹配） | ❌ |

**实现不得在跨页解析中使用几何位置作为依据。**
回退到"位置最接近的"元素，正是 screendiff 跨页静默假匹配的成因。

## 4. 审计

```
audit_diff(prev, cur) -> AuditedDiff
    verdict        : "same_screen" | "different_screen"
    justified      : 身份站得住的匹配
    geometric_only : 只靠几何匹配上的
    false_match_rate
```

**这是本规范的核心价值**：把 screendiff 跨页的静默假匹配变成显式列表。

真实数据：

| 比对 | screendiff 原样 | 审计后 |
|---|---|---|
| home1 vs sub1 | `matched 8` | justified **0** / geometric_only **8** / **false_match_rate 100%** |
| sub1 vs sub2 | `matched 10` | justified **9** / geometric_only **1** / false_match_rate 10% |

`TIER_ANON` 归入 `geometric_only`——两个同 class 的匿名元素在跨页场景下
不构成身份依据。同页那 1 个 geometric_only 正是匿名 ScrollView 对，
保守判假，可接受。

## 5. 实现要求

| 要求 | 级 |
|---|---|
| `same_screen` 只用 snapshot_id | 必须 |
| `shared_keys` 只用内容键，不掺几何 | 必须 |
| 跨页解析只用 `rid` / `label_class` 两级 | 必须 |
| 找不到时返回 not-found，不得几何回退 | 必须 |
| 多候选时必须报 `ambiguous`，不得自动选一个 | 必须 |
| `audit_diff` 不修改 screendiff 的输出 | 必须 |
| 提供 `false_match_rate` | 应该 |
| 结构性 id 不得作为 `rid` tier 依据 | 必须 |

## 6. 已知边界

### 6.1 snapshot_id 不能当换页判据

见 §3.1。id 不等只说明内容变了。要判"换页"，需要别的信号
（例如包名/Activity 变化），本规范不涉及。

### 6.2 匿名元素跨页一律不可信

两个同 class 的匿名元素（如两个 ScrollView）说明不了任何事。
同屏场景下这是**保守的假拒绝**（sub1/sub2 那 1 个就是），可接受。

### 6.3 审计是叠加层，不是修复

`audit_diff` 不改 screendiff 的行为（`test_audit_does_not_modify_screendiff`
钉住这条）。它只是把 screendiff 已经算出的匹配重新标注可信度。

### 6.4 标签变化会被判为不可信

同一行开关从 Off 变 On，`label_class` tier 不成立 → 判 geometric_only。
跨页场景下这是**正确**的保守；同屏场景下则过度保守。
若需要同屏的标签变化检测，用 screendiff 的 `effect()`，不要用本模块。

## 7. 与 screendiff / scrollkey 的分工

| | 回答的问题 | 匹配依据 | 跨页行为 |
|---|---|---|---|
| screendiff | 两份快照怎么比对 | 几何 + 身份 | 会静默假匹配 |
| scrollkey | 一个元素怎么跨快照指代 | 纯内容 | 找不到就找不到 |
| **crosstrack** | **跨页时什么能信** | **只认身份** | **把不信的标出来** |

---

## 验证等级

本资产的量化声明在 **`docs/CLAIMS.md`**（`claimaudit/data/evidence_ledger.json`）登记，
含观测数 / 起始状态数 / 独立通道数 / 是否确定性 / 是否可引用。

复算：`python claimaudit/tools/audit_claims.py`

**规则**（来自 `claimcheck`）：单次观测只能产生假设，不能产生结论；
低于 V1 的声明不得作为结论引用；已推翻（V4）的声明必须留档并标注「不得作为结论」。

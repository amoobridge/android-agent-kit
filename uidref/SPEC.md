# uidref 规范 v0.1

**状态**：Draft
**License**：Apache-2.0
**关键词**：必须（强制）/ 不得（禁止）/ 应该（强烈建议）/ 可以（可选），语义等同 RFC 2119。

---

## 1. 问题陈述

让安卓 agent「点一下设置按钮」。它拿到的是 `uiautomator dump` 的 XML：

- 一次普通设置页 **60-85 个节点、20-29 KB**
- 其中**可交互的只有 5-15 个**（实测 16 个真实界面共 789 节点，可交互 132 个，**16.7%**
——由 `tools/recompute_compression.py` 复算确认；原稿 17.3% 无法复现）
- 每个节点带 17 个属性，绝大多数是 `checkable="false"` 这类噪音

直接喂给模型：token 爆炸、噪声淹没信号、模型还要自己从 bounds 里算中心点。

更糟的是**降噪本身有陷阱**。实测发现：可交互节点**多数是匿名
`LinearLayout`——`text` / `content-desc` / `resource-id` 全空**，文字在子孙
`TextView` 上。任何「只展示有名字的元素」的降噪，都会**静默丢掉大部分可点目标**。

本规范定义一套确定性的「XML → 可交互投影」，让模型**引用元素**而不是猜坐标。

### 1.1 输入子集

实现 必须 支持以下形态，不得 要求更多：

- 根元素 `<hierarchy>`，带 `rotation` 属性（缺省视为 `0`）
- 节点元素标签名恒为 `node`
- 属性用双引号或单引号包裹
- 属性值含 XML 实体（`&amp;` / `&lt;` / `&gt;` / `&quot;` / `&apos;`）
  与数字字符引用（`&#NNN;` / `&#xHH;`）
- 节点可自闭合或含嵌套子节点；文本节点可忽略

实现 **可以** 对畸形输入（未转义的引号、未闭合标签）报错或容忍，
规范不约束——但黄金向量与差分测试只覆盖**合法输入**。
> 实测：Python 的严格 XML 解析器对未转义引号报错，
> 而手写的宽松解析器会接受。这是已知的实现差异，不是规范歧义，
> 因为规范只对合法输入定义行为。

## 2. 核心原则

### 2.1 引用优先于坐标

模型 必须 通过 ref 指代元素，不得 直接给出像素坐标。

```
click e14          而不是        click (540, 1200)
```

理由：坐标需要模型做算术（见 screenpoint 规范），ref 只需要模型认字。

### 2.2 可交互元素一个都不能丢

判定为可交互的节点 必须 全部获得 ref。宁可 digest 变长，不可静默丢弃。

可交互 = 满足任一：

| 条件 | 说明 |
|---|---|
| `clickable="true"` | |
| `long-clickable="true"` | |
| `scrollable="true"` | 滚动容器也要能指，否则模型无法翻页 |
| 类名以 `EditText` 结尾 | 输入框常常 `clickable="false"` |

`enabled="false"` 的节点**仍然算**可交互，且 必须 标 `disabled`。
否则模型会反复点一个死按钮，却看不出为什么没反应。

### 2.3 快照域

ref 只在**产生它的那份快照**内有效。界面一变，旧 ref 一律过期。

实现 必须 在解析不到 ref 时返回明确的 stale 错误，
**不得** 回退到「最近的活元素」——静默点错比报错危险得多。

> **这不是学究气。** 真机验证时点了一下「自动设置时间」开关，
> 下一份快照里「时区」一行从 disabled 变成 enabled。
> 若沿用旧快照的 ref，模型会基于已经失效的状态做决策。

### 2.4 确定性与编号顺序

同一份 XML 必须 产生同一组 ref、同一个 snapshot_id。
否则黄金向量无意义，回归测试会假失败。

ref 编号 必须 按**前序深度优先的文档序**，从 `e1` 起连续递增。
（不是按 bounds 排序、不是按 y 坐标分组——那样同样"确定"，但 ref 会不同，
跨实现对不上。）

## 3. 标签规则

标签优先级，先命中先返回：

| 序 | 来源 | 说明 |
|---|---|---|
| 1 | `text` | |
| 2 | `content-desc` | 无障碍描述，常比 text 更贴意 |
| 3 | `resource-id` 最后一段 | `com.android.settings:id/wifi_settings` → `wifi_settings` |
| 4 | **子孙文本拼接** | 仅当本节点 `clickable="true"` |

### 3.1 结构性 id 不当标签

以下 resource-id 对模型无语义，不得 用作标签。**本集合是穷举的**——
实现 不得 自行扩充，否则同一界面在不同实现下标签不同，破坏 §2.4 的确定性：

```
content            content_parent      decor_content_parent
container          root                main
frame              wrapper             contentPanel
customPanel        parentPanel
```

（带包名前缀的，如 `android:id/content`，取最后一段后同样判定。）

### 3.2 继承只对 clickable 生效

`scrollable="true"` 但 `clickable="false"` 的容器 不得 继承子孙文本。
理由：它的「标签」等于整页内容，是纯噪声。

而 clickable 行 必须 继承——否则匿名行拿到空标签，模型无法区分行与行。

### 3.3 继承的来源与上限

继承取子孙节点的 `text`，**`text` 为空时取该节点的 `content-desc`**。
**跨代**——不限直接子节点，隔代孙也算。
必须 去重且保序（按文档序），必须 有上限（本规范定为 **4 段**，
从"建议"升为 必须：上限不确定则不同实现的 digest 长度不同）。
分隔符 必须 是 ` · `（空格-U+00B7-空格）。

## 4. 角色推断

由类名最后一段后缀匹配。未命中时：

- `clickable="true"` → `item`
- 否则 → `box`

| 类名后缀 | 角色 |
|---|---|
| `EditText` | `input` |
| `CheckBox` / `Switch` / `ToggleButton` / `CompoundButton` | `switch` |
| `RadioButton` | `radio` |
| `SeekBar` | `slider` |
| `RecyclerView` / `ListView` / `AbsListView` | `list` |
| `GridView` | `grid` |
| `ScrollView` / `HorizontalScrollView` | `scroll` |
| `ViewPager` | `pager` |
| `TabWidget` / `TabLayout` | `tabs` |
| `Button` / `ImageButton` / `FloatingActionButton` | `btn` |
| `WebView` | `webview` |
| `ImageView` | `img` |
| `TextView` | `text` |
| 布局类（`LinearLayout` 等） | `box`，clickable 时 `item` |

## 5. bounds 规则

`[x1,y1][x2,y2]` 是**半开区间** `[x1,x2) × [y1,y2)`。

- `x2 < x1` 或 `y2 < y1` → 畸形，必须 跳过
- 面积为 0 → 必须 跳过（点了也没用）
- 负坐标 必须 允许（某些悬浮窗如此）

点击坐标 必须 取中心：`(floor((x1+x2)/2), floor((y1+y2)/2))`。

> **必须 `floor`（向负无穷取整），不是向零截断。**
> SPEC §5 允许负坐标，此时两者相差 1：`floor(-5/2) = -3`，向零截断得 `-2`。
> Python 的 `//` 是 floor，但 JavaScript 的 `|0` 与 `>>1` 是向零截断——
> 跨语言实现若照抄 `//` 的记法就会在这里分叉。
> 实现 不得 用 `ceil` 或其他偏移——中心就是向下取整的除法。

## 6. digest 格式

digest 是给模型看的紧凑文本。首行 必须 含快照标识、包名、屏幕尺寸、
旋转角、元素数：

```
[s39129caee313] com.android.settings 1080x2337 rot=0 elements=10
```

后续每行一个元素：

```
  e8  item   Time zone · GMT+08:00 China Standard Time (disabled)  [0,1607][1080,1813]
```

字段顺序：`ref` / `role` / `label` / `(flags)` / `bounds`。

- 标签为空时 必须 用占位形式 `<role WxH>`，**不得** 留空——
  空行会让模型以为那里有东西
- 标签 必须 有长度上限（建议 60 字符），超出截断加 `...`
- 多标志用逗号连接，置于括号内

## 7. 量化指标

实现 应该 提供 `metrics()`：

| 指标 | 约束 |
|---|---|
| `nodes_total` | 原始节点数 |
| `elements` | 发出的 ref 数 |
| `xml_bytes` / `digest_bytes` | |
| `compression` | 应该 ≥ 10x |
| `est_tokens` | `digest_bytes // 4`，粗略值 |
| `label_coverage` | 有标签元素占比，应该 ≥ 0.7 |

**不设 `actionable_recall` 为可调项**——它是硬规则，必须恒为 1.0（§2.2）。
测试里用独立重算校验，不复用实现自身的判定逻辑。

## 8. HTTP 接口（非规范必需，参考实现提供）

```
GET  /healthz
POST /snapshot   {"xml": "..."} | {"device": "emulator-5554"}
POST /resolve    {"snapshot_id": "...", "ref": "e7"}
POST /tap        {"snapshot_id": "...", "ref": "e7", "device": "..."}
GET  /snapshots
```

参考实现的明确取舍：

1. **默认只绑 `127.0.0.1`**。本服务能代表调用方点击屏幕；
   暴露到局域网等于把设备交给同网段任何人。绑 `0.0.0.0` 必须显式指定。
2. **无认证、无 TLS**。假设运行在本机、只服务本机客户端。
3. **stale ref 返回 HTTP 409**，响应体含 `stale_ref` 与重新 snapshot 的提示。
4. **`uiautomator dump` 是异步的**：命令返回时文件常未落盘，
   紧接着 `cat` 会读到空串。参考实现轮询等待，最多 5 次。

## 9. 已知不在本规范范围内

- **WebView / Flutter / 自绘 UI**：无障碍树常为空或只有一层容器。
  此时 uidref 只能给出容器 ref，内容需靠视觉。这是已知边界。
- **树太大**：超长列表一次 dump 可能仍上千节点。本规范只做「可交互投影」，
  不做分页或虚拟化。滚动由 §2.2 的 scrollable ref 驱动，但翻页后必须重新 snapshot。
- **ref 跨快照复用**：明确不做。见 §2.3。

---

## 10. 一致性（Conformance）

实现**声称符合本规范**，必须满足以下全部条件。

### 10.1 一致性条件

| # | 条件 |
|---|---|
| C1 | 通过本规范随附的**全部**黄金向量（`vectors/`，45 条，7 个文件） |
| C2 | 输出的字段集合与类型**完全匹配**契约——缺字段、类型错误均不算通过 |
| C3 | 同一输入重复解析，输出**逐字段相同**（§2.4） |
| C4 | 在 16 个真实 dump（`dumps/`）上的输出与参考实现**逐字段相同** |

> C2 与 C4 不可省。历史教训：一致性测试曾对一个**向零截断 center** 的实现
> 全绿放行——因为当时的比对契约里**根本没有 center 字段**。
> 字段缺失会让整个验证对真实分歧失明。

### 10.2 一致性级别

| 级别 | 要求 | 适用 |
|---|---|---|
| **Level 1** | C1 + C2 | 最小可用。仅证明规则在已知输入上可判定 |
| **Level 2** | C1 + C2 + C3 | 增加确定性证明 |
| **Level 3（完整）** | C1 + C2 + C3 + C4 | 证明在**真实数据**上与参考实现一致 |

**只有 Level 3 可以声称「完整符合本规范」。**

### 10.3 如何验证

```bash
# 语言无关：任何「XML 进 JSON 出」的命令都能测
python tools/verify_impl.py vectors/ --cmd "node js/impl.js"
```

契约字段与用法见 `docs/PORTABILITY.md` §4。

### 10.4 规范的已知边界

见 §9（WebView/Flutter/自绘 UI、超长列表、ref 跨快照复用）。
在这些边界内，规范**不保证**行为，实现可自行决策。

---

## 11. 可移植性证据

本规范的条文经过**两种语言的独立实现**交叉验证。
证据与方法论详见 `docs/PORTABILITY.md`。

| 证据 | 结果 |
|---|---|
| 黄金向量 45 条 × 2 语言 | Python 45/45 · JavaScript 45/45 |
| 16 个真实 dump 逐字段比对 | 完全一致 |
| 随机差分 5 seed × 200 条 | 0 分歧 |
| 元测试（含变异敏感性） | 5 条，已反向验证 |

**独立实现逼出的规范修订**（这些是规范的改进，不是实现的补丁）：

| # | 位置 | 原条文的问题 | 现条文 |
|---|---|---|---|
| A1 | §5 | 写 `//2` 借用 Python 语法，JS 的 `\|0`/`>>1` 向零截断，负坐标下差 1 | 必须 floor |
| A2 | §3.1 | 「**等**结构性容器名」是开口，各实现自行扩充破坏确定性 | 穷举 + 不得 扩充 |
| A3 | §1 | 未定义输入域 | 新增 §1.1 输入子集 |
| A4 | §2.4 | 只说"确定"没说编号顺序 | 前序深度优先文档序 |
| A5 | §3.3 | 未说继承来源、是否跨代、上限只是"建议" | 明确，上限升 必须 |

---

---

## 验证等级

本资产的量化声明在 **`docs/CLAIMS.md`**（`claimaudit/data/evidence_ledger.json`）登记，
含观测数 / 起始状态数 / 独立通道数 / 是否确定性 / 是否可引用。

复算：`python claimaudit/tools/audit_claims.py`

**规则**（来自 `claimcheck`）：单次观测只能产生假设，不能产生结论；
低于 V1 的声明不得作为结论引用；已推翻（V4）的声明必须留档并标注「不得作为结论」。

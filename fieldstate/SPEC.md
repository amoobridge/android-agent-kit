# fieldstate 规范 · 安卓输入框状态判定

**版本** 0.1.0 · **日期** 2026-10-27 · **License** Apache-2.0
**测试环境** AVD `avd-api35`（Android 15 / Google APIs / arm64-v8a），emulator-5554

**关键词**：必须（MUST）/ 不得（MUST NOT）/ 应该（SHOULD）/ 可以（MAY）。
---

## 0. 这个问题是什么

每一个要把文本写进输入框的 GUI agent，在写之前都要回答四个问题：

| | 问题 | 常见 ad-hoc 做法 |
|---|---|---|
| **D1** | 这个字段**是空的吗**？ | `text == ""` |
| **D2** | 它**聚焦了吗**？ | `focused == "true"` |
| **D3** | 它**能写吗**？ | class 名含 `EditText` |
| **D4** | 我**清干净了吗**？ | 发 60 个 DEL |

四个都有 silent failure。其中 D1 的最严重，且**几乎所有人都在犯**。

---

## 1. D1：`text == ""` 判定字段为空是错的

### 1.1 真机证据

AVD Android 15，设置页搜索框（`open_search_view_edit_text`），**同一个节点、同一个字段**：

| 字段真实状态 | XML `text` 属性 | 无障碍 API `isShowingHintText()` |
|---|---|---|
| **空**（显示 hint） | `"Search settings"` | **`true`** |
| 有内容 `PROBE` | `"PROBE"` | **`false`** |
| **空**（无 hint） | `""` | `true` |

> 复现：`textin/refapp` + `adb shell am broadcast -a com.textin.refapp.PROBE_STATE`，
> 读 `run-as com.textin.refapp cat files/last_state.json`。

> **更正（2026-10-27）**：原稿写「XML 序列化在空格处断开，属性值里
> 出现裸换行符」——**这是错的，已用逐字节 hex 证实**。
> 实测 `fieldstate/data/state1_empty_with_hint.xml` 的 `text` 属性值
> `hex = 5365617263682073657474696e6773`，即 `Search settings`，
> **0x20 空格，没有任何 0x0a 换行符**。
> 原稿那个"换行"是终端把空格显示断行造成的视觉误判。
>
> 更正后的准确表述：**XML 的 `text` 属性在字段为空时报告 hint 原文
> `"Search settings"`，与真实内容的形态完全无法区分**——这才是问题本身，
> 比"有个换行符"更根本，因为连 hex 层面都看不出区别。

### 1.2 后果

agent 看到 `text = "Search settings"`，判定"字段非空"，于是：

- **跳过写入** → 用户的搜索词从来没进去，agent 以为写过了
- 或者**先清场再写**，而清场逻辑又基于 `text != ""` 判断"有没有内容可清"
  → 它确实在清，清的是 hint 的位置，字段本来就是空的

两条路都**不产生任何异常信号**。这是 silent failure。

### 1.3 根因

`AccessibilityNodeInfo.getText()` 对 TextView/EditText 的语义是：
**文本为空时回落到 hint**。这是有意的——TalkBack 需要念出 hint 告诉盲人
这个框是干什么的。

但 `uiautomator dump` 的 XML **不带 hint 本身**，也不带
`isShowingHintText()`。于是消费者拿到的 `text` 是一个**二义值**：

```
text 非空  ⟺  字段有内容   OR  字段为空且有 hint
```

没有任何字段能区分这两支。

### 1.4 XML dump 到底暴露了什么（全量清点）

对同一个 EditText 节点，`uiautomator dump` 给出的全部属性：

```
index, text, resource-id, class, package, content-desc,
checkable, checked, clickable, enabled, focusable, focused,
scrollable, long-clickable, password, selected, bounds
```

**以下字段 XML 一律不暴露**：

| 缺失字段 | 无障碍 API 有吗 | 用途 |
|---|---|---|
| `hint` | 无独立 getter | 无法把 hint 与真实文本分开 |
| `isShowingHintText` | ✅ `isShowingHintText()` | **D1 的正确答案** |
| `textSelectionStart/End` | ✅ | 次选判据（空字段 = -1） |
| `editable` | ✅ `isEditable()` | D3 的正确答案 |
| `cursorVisible` | ✅ | 仅 IME 可见时有意义 |
| `inputType` | ✅ `getInputType()` | 单行/多行、数字、密码 |

**结论：`uiautomator dump` 的 XML 是有损的。** 它丢了恰好是判定所必需的字段。

### 1.5 正确判定

| 层 | D1 判定 | 可靠度 |
|---|---|---|
| **XML dump** | 无可靠判据。`text == ""` 只在"字段无 hint"时成立 | ❌ |
| **无障碍 API** | `!isShowingHintText()` | ✅ 精确 |
| **无障碍 API（次选）** | `textSelectionStart >= 0` | ✅ 精确 |

> **C1**：主张"字段为空"的实现不得只用 `text` 为空字符串作判据。
> **C1a**：若只能拿到 XML dump，必须在文档里声明该判据不可靠，
> 且应该用启发式（如属性值含裸换行符）并标注为启发式。

---

## 2. D2：聚焦判定

### 2.1 真机证据

| 状态 | XML `focused` | API `isFocused()` |
|---|---|---|
| 点击后 | `"true"` | `true` |
| 全新打开未点击 | `"true"` | `true` |

`focused` 在 XML 里可用，且与 API 一致。**这一项没有发现 silent failure。**

### 2.2 但 `focusable` 不等于 `focused`

`focusable="true"` 只说"这个节点**可以**获得焦点"，不说明它**现在有**。
判定聚焦必须用 `focused`，不是 `focusable`。

> **C2**：D2 判定必须用 `focused`，不得用 `focusable`。

### 2.3 聚焦不等于可写

聚焦只是光标在里面。字段仍可能是只读的（`isEditable() == false`）。
`ACTION_SET_TEXT` 对只读字段不会生效。

> **C3**：D3 判定必须用 `isEditable()`；XML 层只能用 class 名含
> `EditText` 作**启发式**，且必须标注为启发式。

---

## 3. D4：清场判定

### 3.1 三条路都不干净

| 路 | 做法 | 问题 |
|---|---|---|
| A | 发 N 个 `KEYCODE_DEL` | N 取多少？发少了清不净，发多了慢 |
| B | `ACTION_SET_TEXT("")` | **空 extra 根本送不到**（见 §3.2） |
| C | 全选 + DEL | 全选本身依赖输入法，不一定有 |

### 3.2 ★ 空 extra 送不到

实测：`adb shell am broadcast -a ... --es text_b64 ""` → **`am` 自己抛异常**，
广播没有发出去：

```
at android.os.Binder.execTransactInternal(Binder.java:1505)
at android.os.Binder.execTransact(Binder.java:1444)
```

字段内容原样保留。

**这不是无障碍 API 的问题，是 adb 命令行的问题。**
`input text` 也清不了空（空参数同样送不到）。

> **C4**：清场不得依赖"发送空文本"——空 extra 在
> `am broadcast --es` 与 `input text` 两条路上都送不到。
> **C4a**：清场应该用 `KEYCODE_DEL`，且轮数必须由回读判定收敛，
> 不写死。

### 3.3 正确做法：删到不再变化

```
baseline = None
repeat:
    read text
    if text == baseline: stop        # 不再变化 = 清干净了
    baseline = text
    send 一批 KEYCODE_DEL
```

textin 的 `../textin/tools/compare_paths.py` 用这条，实测 12 轮内收敛。

> **C5**：清场的收敛判据必须是"回读不再变化"，不得是固定轮数。

### 3.4 但清完之后你还不知道它是不是空的

DEL 清干净后，`text` 立刻变成 hint（§1.1）。
所以**清场成功 ≠ `text == ""`**。清场判据用的是"不再变化"，
而"是否为空"必须回到 §1.5 的 `isShowingHintText()`。

> **C6**：D4（清干净了吗）与 D1（是空的吗）是两个问题，
> 必须用不同判据，不得互相替代。

---

## 4. 参考实现（XML 层）

`core.py` 提供两个函数：

- `state_from_xml(node)` —— 只吃 XML 节点，返回 `FieldState`
- `verdict(state)` —— 给出 D1–D4 的判定，并标注每个判定的可靠度

XML 层的 D1 **没有可靠答案**，参考实现返回 `unknown` 而不是猜。

```python
from fieldstate import state_from_xml, verdict
import xml.etree.ElementTree as ET

node = ...  # 一个 <node> 元素
st = state_from_xml(node)
v = verdict(st)
# v["d1"] == "unknown"      # XML 层判不出空与非空
# v["d1_reliable"] == False
# v["d2"] == "focused"
# v["d3"] == "writable_heuristic"
```

---

## 5. 参考实现（API 层）

`fieldstate` 不绑定任何 Android 侧实现。契约见
`textin/refapp` 的 `PROBE_STATE` 广播：它回一个 JSON，字段名固定：

| 字段 | 类型 | 来源 |
|---|---|---|
| `focus` | `"input"` / `"none"` | — |
| `is_editable` | bool | `AccessibilityNodeInfo.isEditable()` |
| `is_showing_hint_text` | bool | `AccessibilityNodeInfo.isShowingHintText()` |
| `text_selection_start` | int | `getTextSelectionStart()` |
| `text_selection_end` | int | `getTextSelectionEnd()` |
| `is_focused` | bool | `isFocused()` |
| `text` | string | `getText()` |

> **C7**：API 层 JSON 的字段名必须与上表一致，以便不同后端互换。

> **C8**：`focused`（归一结果）必须优先于
> `is_focused`（原始布尔）作为 D2 判据。
>
> 理由：`focus == "none"` 表示**根本没找到焦点输入节点**，是比
> `isFocused()` 更强的信号。`state_from_api` 已把它归一成 `focused="false"`；
> 若 D2 仍优先读原始布尔，后端给出 `focus="none"` 同时
> `is_focused=true`（脏数据 / 陈旧快照）时，会把「没有焦点输入节点」
> 报成 focused。

---

## 6. 一致性条件

| # | 条件 |
|---|---|
| C1 | D1 不得只用 `text` 为空字符串作判据 |
| C1a | 只有 XML 时必须声明判据不可靠；启发式必须标注 |
| C2 | D2 必须用 `focused`，不得用 `focusable` |
| C3 | D3 必须用 `isEditable()`；class 名启发式必须标注 |
| C4 | 清场不得依赖发送空文本 |
| C4a | 清场轮数必须由回读收敛，不得写死 |
| C5 | 清场收敛判据必须是"回读不再变化" |
| C6 | D4 与 D1 必须用不同判据 |
| C7 | API 层 JSON 字段名必须与 §5 一致 |

**一致性级别**

| 级别 | 条件 |
|---|---|
| Level 1 | C1, C2, C6 |
| Level 2 | Level 1 + C1a, C3, C4, C4a, C5 |
| Level 3 | Level 2 + C7 |

---

## 7. 边界

1. **取证来自一台 AVD（Android 15 / Google APIs）的一个字段**
   （设置页搜索框）。**换设备需重跑**，不要假定数字一致。
   结论的方向性——hint 回落进 `getText()`——来自
   `AccessibilityNodeInfo` 的公开语义，跨设备应成立；**精确现象**
   （如那个裸换行符）不应外推。
2. **只测了单行 EditText。** 多行（`inputType` 含 `textMultiLine`）下
   hint 回落行为、以及真实文本含换行时的表现**未测**。
3. **`isShowingHintText()` 未经其他 ROM 验证。**
4. **裸换行符启发式不可靠**：如果用户真的输入了含换行的文本
   （多行框），该启发式会误判。规范不推荐用它，只记录它存在。
5. **`uiautomator dump` 只捕获活动窗口。** 别的 App 里的字段看不到。

---

## 验证等级

本资产的量化声明在 **`docs/CLAIMS.md`**（`claimaudit/data/evidence_ledger.json`）登记，
含观测数 / 起始状态数 / 独立通道数 / 是否确定性 / 是否可引用。

复算：`python claimaudit/tools/audit_claims.py`

**规则**（来自 `claimcheck`）：单次观测只能产生假设，不能产生结论；
低于 V1 的声明不得作为结论引用；已推翻（V4）的声明必须留档并标注「不得作为结论」。

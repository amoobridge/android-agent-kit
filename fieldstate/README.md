# fieldstate · 安卓输入框状态判定

**License** Apache-2.0 · **版本** 0.1.0 · **日期** 2026-10-27
**测试环境** AVD `avd-api35`（Android 15 / Google APIs / arm64-v8a）

---

## 一句话

**字段是空的，`text` 却非空——因为空字段会把 hint 报进 `text`。**
`text == ""` 判定字段为空是错的，而 `uiautomator dump` 的 XML
**不给任何能区分这两者的字段**。

---

## 核心证据

AVD Android 15，设置页搜索框，**同一个节点、同一个字段**：

| 字段真实状态 | XML `text` | `isShowingHintText()` | `textSelectionStart` |
|---|---|---|---|
| **空**（显示 hint） | `"Search settings"` | **`true`** | **`-1`** |
| 有内容 `PROBE` | `"PROBE"` | **`false`** | `5` |
| **空**（无 hint） | `""` | `true` | `-1` |

> **更正（2026-10-27）**：原稿称「XML 序列化在空格处断开、
> 属性值里出现裸换行符」——**错的**，已逐字节 hex 证实
> （`5365617263682073657474696e6773` = `Search settings`，0x20 空格，无 0x0a）。
> 那个"换行"是终端显示造成的视觉误判。
>
> 准确表述：字段为空时，XML 的 `text` 属性报告 hint 原文
> `"Search settings"`，**与真实内容在 hex 层面都无法区分**。

复现：`textin/refapp` 的 `PROBE_STATE` 广播 +
`adb shell run-as com.textin.refapp cat files/last_state.json`。

---

## 后果：一个 silent failure

agent 看到 `text = "Search settings"`，判定"字段非空"：

- **跳过写入** → 用户的搜索词从来没进去，agent 以为写过了
- 或**先清场再写**，而清场又基于 `text != ""` 判断有没有内容可清

两条路都**不产生任何异常信号**。

---

## 根因

`AccessibilityNodeInfo.getText()` 对 TextView/EditText 的语义是
**文本为空时回落到 hint**。这是有意的——TalkBack 要念出 hint 告诉盲人
这个框干什么。

但 `uiautomator dump` 的 XML **不带 hint 本身**，也不带
`isShowingHintText()`。于是 `text` 是个**二义值**：

```
text 非空  ⟺  字段有内容   OR   字段为空且有 hint
```

### XML dump 到底暴露了什么（全量清点）

对同一个 EditText 节点，dump 给出的全部属性：

```
index, text, resource-id, class, package, content-desc,
checkable, checked, clickable, enabled, focusable, focused,
scrollable, long-clickable, password, selected, bounds
```

**以下字段 XML 一律不暴露**：

| 缺失字段 | 无障碍 API 有吗 | 用途 |
|---|---|---|
| `hint` | 无独立 getter | 无法把 hint 与真实文本分开 |
| `isShowingHintText` | ✅ | **D1 的正确答案** |
| `textSelectionStart/End` | ✅ | 次选判据（空 = -1） |
| `editable` | ✅ `isEditable()` | D3 的正确答案 |
| `cursorVisible` | ✅ | 仅 IME 可见时有意义 |
| `inputType` | ✅ `getInputType()` | 单行/多行、数字、密码 |

**结论：`uiautomator dump` 的 XML 是有损的。** 它丢的恰好是判定所必需的字段。

---

## 四个判定

| | 问题 | 常见 ad-hoc | 本规范 |
|---|---|---|---|
| **D1** | 字段是空的吗 | `text == ""` | `!isShowingHintText()`；XML 层 **unknown** |
| **D2** | 聚焦了吗 | `focused` | `focused`（**不是** `focusable`） |
| **D3** | 能写吗 | class 含 `EditText` | `isEditable()`；class 名是启发式 |
| **D4** | 清干净了吗 | 发 60 个 DEL | 删到回读不再变化 |

D4 有一条独立发现：**空 extra 送不到**。
`adb shell am broadcast -a ... --es text_b64 ""` 会让 `am` 自己抛异常
（`Binder.execTransact`），广播根本没发出去，字段内容原样保留。
`input text` 同样送不了空参数。
所以清场 不得 依赖"发送空文本"。

---

## 参考实现

```python
from fieldstate import state_from_xml, verdict
import xml.etree.ElementTree as ET

node = ET.parse("dump.xml").getroot().find(".//node")
v = verdict(state_from_xml(node))

# XML 层：
#   v["d1_is_empty"]          == "unknown"        # 判不出，不猜
#   v["d1_reliable"]          == False
#   v["d2_is_focused"]        == "focused"
#   v["d3_is_writable"]       == "writable_heuristic"
#   v["d3_reliable"]          == False
```

API 层（`textin/refapp` 的 `PROBE_STATE` JSON）：

```python
v = verdict(state_from_api({
    "focus": "input", "is_editable": True,
    "is_showing_hint_text": True, "text_selection_start": -1,
    "is_focused": True, "text": "Search settings"}))
#   v["d1_is_empty"] == "empty"    v["d1_reliable"] == True
```

**设计原则：判不出就说判不出。** XML 层 D1 返回 `unknown` 而不是猜。
一个会说"我不知道"的库，比一个给出自信错答案的库有用。

---

## 目录

```
fieldstate/
├── SPEC.md          规范：四个判定 + 真机证据 + 一致性条件 C1–C7
├── README.md        本文件
├── core.py          参考实现（XML 层 / API 层）
├── vectors.py       黄金向量（XML 层 6 + API 层 6 + 判别器 2）
├── tests/           53 条 pytest
├── tools/
│   └── probe_field_state.py   真机勘察：XML 暴露了什么
└── data/
    └── field_state.json       勘察结果
```

## 测试

```bash
cd fieldstate
python -m pytest tests/ -q          # 53 passed
```

`TestNotVacuous` 用变异敏感性防"用例空转"（uidref 曾有 12 条向量全绿
但一条都没测到东西）。其中一条是**反向元测试**：
`focusable` 变异**不得**改变 D2 的结论——如果它改变了，说明实现违规
用了 `focusable`，违反 C2。

---

## 边界

1. 取证来自**一台 AVD 的一个字段**（设置页搜索框）。换设备需重跑。
   结论的方向性（hint 回落进 `getText()`）来自 `AccessibilityNodeInfo`
   的公开语义，跨设备应成立；**精确现象**（那个裸换行符）不应外推。
2. 只测了**单行 EditText**。多行框下 hint 回落行为、以及真实文本含换行时
   的表现**未测**。
3. `isShowingHintText()` 未经其他 ROM 验证。
4. **裸换行符启发式不可靠**：多行框里用户真输入换行时会误判。
   规范记录它存在，但不推荐。
5. `uiautomator dump` 只捕获**活动窗口**，别的 App 里的字段看不到。

---

## 适用范围

**本库定位**：Apache-2.0，无第三方应用依赖，命名中性。
作为「GUI agent 怎么判断输入框状态」的最小可复用层，
对同类项目有直接参考价值。核心证据（hint 回落 + XML 有损）
是可复现的真机事实，不是观点。

---

## 验证等级

本资产的量化声明在 **`docs/CLAIMS.md`**（`claimaudit/data/evidence_ledger.json`）登记。

复算：`python claimaudit/tools/audit_claims.py`

**规则**（来自 `claimcheck`）：单次观测只能产生假设，不能产生结论；
低于 V1 不得作为结论引用；已推翻（V4）必须留档并标注「不得作为结论」。

# imespec 规范 · 键盘遮挡与元素可及性判定

**版本** 0.1.0 · **日期** 2026-10-27 · **License** Apache-2.0
**测试环境** AVD `avd-api35`（Android 15 / Google APIs / arm64-v8a），emulator-5554

**关键词**：必须（MUST）/ 不得（MUST NOT）/ 应该（SHOULD）/ 可以（MAY）。
---

## 0. 这个问题是什么

agent 点了一个元素，界面没反应。它以为点偏了，或者以为 App 卡了。

**真实原因可能是：键盘正压在它上面。**

一个元素报着合法的 `bounds` 和 `clickable=true`，点下去却命中键盘。
**XML 不给任何信号。**

---

## 1. 真机证据

AVD Android 15，设置页搜索，输入 `net`，键盘弹起
（`dumpsys input_method` → `mInputShown=true`）。

### 1.1 键盘是独立窗口，XML 里没有它

`AccessibilityWindowInfo`（无障碍服务 `getWindows()`）返回 **4 个窗口**：

| type | layer | title | bounds_in_screen |
|---|---|---|---|
| 3 SYSTEM | 3 | `null` | `0 0 1080 74` |
| 1 APPLICATION | 2 | `Popup Window` | `221 261 326 366` |
| **2 INPUT_METHOD** | 1 | **`English (US) (QWERTY)`** | **`0 1517 1080 2400`** |
| 1 APPLICATION | 0 | `Settings Services` | `0 0 1080 2400` |

**type == 2（`TYPE_INPUT_METHOD`）就是键盘**，占屏幕
`y ∈ [1517, 2400]` = **36.8%**。

而同一时刻 `uiautomator dump` 的 XML 有 **35 个节点，package 全是
`com.google.android.settings.intelligence`** —— **键盘一个节点都没有。**

### 1.2 App 窗口不收缩

注意上表最后一行：App 窗口的 bounds 仍是 `0 0 1080 2400`，
**没有因为键盘弹起而缩小**。

所以 XML 里所有元素的 bounds 保持原样，看起来完全正常。

### 1.3 ★ 但 38.5% 的可点元素点不到

XML 报 `clickable=true` 的节点共 13 个，与键盘区域求交：

| bounds | 遮挡比 | 结论 |
|---|---|---|
| `[0,136][126,325]` | 0% | reachable |
| `[126,136][933,325]` | 0% | reachable |
| `[933,157][1080,304]` | 0% | reachable |
| `[0,328][1080,551]` ~ `[0,1220][1080,1384]` | 0% | reachable |
| `[0,1384][1080,1548]` | **18.9%** | partially_occluded |
| `[0,1548][1080,1712]` | **100%** | **occluded** |
| `[0,1712][1080,1935]` | **100%** | **occluded** |
| `[0,1935][1080,2158]` | **100%** | **occluded** |
| `[0,2158][1080,2381]` | **100%** | **occluded** |

**5/13 = 38.5% 的可点元素被键盘挡住，其中 4 个完全压住。**

agent 想点列表底部的某一项（比如 y=2017 的"Allow WEP networks"），
点下去命中键盘。**没有异常、没有错误、点击"成功"了。**

### 1.4 复现

```bash
adb -s emulator-5554 shell am start -a android.settings.APP_SEARCH_SETTINGS
adb -s emulator-5554 shell input tap 530 230          # 聚焦，键盘弹起
adb -s emulator-5554 shell am broadcast -a com.textin.refapp.SET_TEXT \
    --es text_b64 "$(printf 'net' | base64)"
adb -s emulator-5554 shell am broadcast -a com.textin.refapp.LIST_WINDOWS
adb -s emulator-5554 shell run-as com.textin.refapp cat files/last_windows.json
adb -s emulator-5554 shell uiautomator dump --compressed /data/local/tmp/x.xml
adb -s emulator-5554 exec-out cat /data/local/tmp/x.xml
```

或直接用本库的探针（自动抓两份并复算）：

```bash
python tools/probe_ime.py
```

---

## 2. 根因

两层：

1. **IME 是独立窗口**（`TYPE_INPUT_METHOD`），
   `uiautomator dump` 只捕获**活动 App 窗口**，所以键盘不在 XML 里。
2. **App 窗口不收缩**（本环境 `adjustPan` 语义），
   所以元素 bounds 不变，遮挡无从显现。

TalkBack 能正确处理这件事，因为它运行在**无障碍服务**里，
拿得到 `getWindows()` 的完整窗口列表。而基于 `uiautomator dump` 的
agent 拿不到。

---

## 3. 判定

### 3.1 遮挡比

```
occlusion = overlap_area(element, ime) / area(element)
```

### 3.2 可及性

| 遮挡比 | 结论 |
|---|---|
| `== 0` | `reachable` |
| `(0, 1)` | `partially_occluded` |
| `>= 1` | `occluded` |

边界：恰好 1.0 判 `occluded`。

### 3.3 ★ 拿不到键盘信息时：`unknown`

**只有 XML 时，不得假定键盘不在。**

理由：键盘是否弹起与 agent 上一个动作强相关（刚点了输入框？刚写了文本？），
而 XML 完全不反映这件事。猜"没键盘"会让 agent 点空气；
猜"有键盘"会让它在正常场景下拒绝点击。

> **C1**：没有 IME 窗口信息时，可及性必须报 `unknown`，
> 不得假定键盘未弹起。
> **C1a**：只有 XML 时，应该在报告里显式声明
> 「键盘状态未知」，而不是静默跳过。

### 3.4 IME 判据是 type，不是标题

标题是输入法的名字（`English (US) (QWERTY)`），随用户安装的输入法而变，
**不能当判据**。判据是 `type == TYPE_INPUT_METHOD (2)`。

> **C2**：识别 IME 窗口必须用 `type == TYPE_INPUT_METHOD`，
> 不得用标题匹配。

---

## 4. 拿不到无障碍服务怎么办

| 途径 | 能否判定 | 说明 |
|---|---|---|
| `AccessibilityWindowInfo` | ✅ 精确 | 需无障碍权限；`uidref` 读取侧已在用同一把钥匙 |
| `dumpsys input_method` | ✅ 精确 | **调试命令，不是公开 API**，正式实现不得依赖 |
| `uiautomator dump` XML | ❌ 不可能 | 键盘不在 XML 里 |
| `adb shell dumpsys window` | ✅ 精确 | 同样非公开 API |

> **C3**：正式实现必须用 `AccessibilityWindowInfo`。
> `dumpsys` 系列仅可用于取证与测试，不得出现在生产路径。

### 4.1 一个负发现

`AccessibilityService` **没有** IME 状态访问器。
`InputMethodManager.isAcceptingText()` 不在该服务的可用 API 里
（且 API 33+ 已 deprecated/受限）。**公开无障碍 API 不提供
"键盘是否弹出"的直接查询**——只能通过窗口列表间接得到。

这条负发现已记录在 `textin/refapp/src/.../SetTextService.java`
的 `reportWindows()` 注释里。

---

## 5. 参考实现

```python
from imespec import audit_xml, audit_from_files, ime_from_windows, ime_rect
import xml.etree.ElementTree as ET

# 有窗口信息（无障碍服务）
wins = {"windows": [...]}          # getWindows() 序列化
ime = ime_rect(ime_from_windows(wins["windows"]))
root = ET.parse("dump.xml").getroot()
r = audit_xml(root, ime)
# r["unreachable_count"] == 5, r["unreachable_ratio"] ≈ 0.385

# 只有 XML
r = audit_xml(root, None)
# r["ime_known"] == False
# r["items"][0]["reachability"] == "unknown"     ← 不猜
```

---

## 6. 一致性条件

| # | 条件 |
|---|---|
| C1 | 没有 IME 窗口信息时，可及性必须报 `unknown`，不得假定键盘未弹起 |
| C1a | 只有 XML 时应该显式声明「键盘状态未知」，不静默跳过 |
| C2 | 识别 IME 必须用 `type == TYPE_INPUT_METHOD`，不得用标题匹配 |
| C3 | 正式实现必须用 `AccessibilityWindowInfo`；`dumpsys` 仅限取证 |
| C4 | 遮挡比必须按面积算，不得用 y 坐标大小比较 |
| C5 | 遮挡比恰好 1.0 必须判 `occluded` |
| C6 | `parse_bounds` 必须正确处理 `[x1,y1][x2,y2]` 内部的逗号 |

**一致性级别**

| 级别 | 条件 |
|---|---|
| Level 1 | C1, C2, C4 |
| Level 2 | Level 1 + C1a, C3, C5, C6 |

---

## 7. 边界

1. **取证来自一台 AVD、一个界面、一个输入法。**
   不同 ROM、不同输入法、不同 App 的 `windowSoftInputMode`
   （`adjustResize` / `adjustPan` / `adjustNothing`）会改变结论。
   **换设备需重跑 `tools/probe_ime.py`**，不要假定遮挡比一致。
2. **只测了 `adjustPan` 语义**（App 窗口不收缩）。
   若某 App 用 `adjustResize`，窗口会缩小、元素 bounds 会变，
   遮挡情况不同——**那种情况下遮挡可能不出现，但 bounds 已变**，
   那是另一类问题（uidref 的 `snapshot_id` 会变）。
3. **多窗口 / 分屏 / 画中画未测。**
4. **IME 窗口 bounds 的坐标系是屏幕坐标**，与 XML 的 bounds 一致。
   若未来遇到多显示器，需另议。
5. **本规范不处理"怎么把键盘收起来"。** 那属于 act 侧，
   且 `KEYCODE_BACK` 是最常用的手段，但它同时会触发返回逻辑——
   副作用不在本规范范围内。

---

## 8. 与其他库的关系

| 库 | 关系 |
|---|---|
| `uidref` | uidref 给 ref 和 digest；imespec 给这些 ref 的**可及性** |
| `fieldstate` | fieldstate 判"字段能否写"；imespec 判"点了会不会命中键盘" |
| `textin` | textin 判"文本怎么送进去"；imespec 判"送进去之后 UI 变成什么样" |
| `screendiff` | 键盘弹起/收起是一次界面变化，screendiff 的 `is_loading` 之类判据不覆盖它 |
| `devapi` | `/v1/act` 在执行前应查可及性；本规范提供判据 |

**imespec 是横切关注点**：它不产出新能力，只是让已有的点击能力
**不说谎**。

---

## 验证等级

本资产的量化声明在 **`docs/CLAIMS.md`**（`claimaudit/data/evidence_ledger.json`）登记，
含观测数 / 起始状态数 / 独立通道数 / 是否确定性 / 是否可引用。

复算：`python claimaudit/tools/audit_claims.py`

**规则**（来自 `claimcheck`）：单次观测只能产生假设，不能产生结论；
低于 V1 的声明不得作为结论引用；已推翻（V4）的声明必须留档并标注「不得作为结论」。

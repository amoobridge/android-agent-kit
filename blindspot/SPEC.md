# blindspot 规范 · XML dump 的非 App 窗口盲区

**版本** 0.1.0 · **日期** 2026-10-27 · **License** Apache-2.0
**测试环境** AVD `avd-api35`（Android 15 / Google APIs / arm64-v8a），emulator-5554

---

## 0. 这个问题是什么

agent 点了一个 XML 说 `clickable=true` 的元素。**点下去命中的是键盘。**

真机实测：搜索框内容从 `net` 变成 `netv`——点击落在键盘的 `v` 键上，
向搜索框写入了一个字符。agent 想点的目标（"Allow WEP networks" 行）
**完全没有被触发**。

而且：如果 agent 只比较"界面是否变化"，它会看到变化
（搜索框内容变了），**可能误判为点击生效**。

---

## 1. 核心发现：两条感知通道不一致

agent 有两条通道看屏幕：

| 通道 | 命令 | 完整？ |
|---|---|---|
| 截图 | `adb shell screencap` | **完整**，含键盘 |
| 结构 | `adb shell uiautomator dump` | **有损**，看不见键盘 |

### 1.1 截图包含键盘（边界精确到像素）

键盘弹起时 `screencap` 得到 1080×2400 图像。逐行取色：

```
y=1500  rgb(232,231,239)   ← App 背景
y=1509  rgb(231,230,238)   ┐
y=1510  rgb(230,229,237)   │ 16 像素渐变（阴影）
...
y=1516  rgb(223,222,230)   ┘
y=1517  rgb(241,240,247)   ← 键盘背景（比 App 亮）
y=1600  rgb(241,240,247) + rgb(176,198,255) + rgb(255,255,255)   ← 按键
y=2000  rgb(255,255,255)x13                                        ← 白色按键
```

**键盘起点 y=1517，与 `AccessibilityWindowInfo` 报的 IME bounds
`0 1517 1080 2400` 精确相等。**

### 1.2 XML 完全没有键盘

同一时刻 `uiautomator dump` 有 35 个节点，**package 全是
`com.google.android.settings.intelligence`**——键盘一个节点都没有。

### 1.3 ★ 于是 38.5% 的可点元素是幻影

XML 报 `clickable=true` 的 13 个节点，与键盘区域求交：

| bounds | 遮挡比 | 结论 |
|---|---|---|
| `[0,1384][1080,1548]` | 18.9% | 部分 |
| `[0,1548][1080,1712]` | **100%** | 完全 |
| `[0,1712][1080,1935]` | **100%** | 完全 |
| `[0,1935][1080,2158]` | **100%** | 完全 |
| `[0,2158][1080,2381]` | **100%** | 完全 |

**5/13 = 38.5% 不可及，其中 4 个完全被键盘压住。**

而 App 窗口 bounds 仍是 `0 0 1080 2400`（没收缩），
所以 XML 里这些元素的 bounds 看起来完全正常。

---

## 2. 行为后果（决定性证据）

```
状态     搜索框 text
点击前   "net"
点击后   "netv"      ← 点了 XML 说可点的 [0,1935][1080,2158]
```

点击坐标 (540, 2017) 落在键盘的 `v` 键上。
**agent 的点击被键盘接收，并向 App 写入了它没打算写入的数据。**

这不只是"没反应"，是**静默的状态污染**。

---

## 3. 根因

1. **IME 是独立窗口**（`TYPE_INPUT_METHOD`），
   `uiautomator dump` 只捕获**活动 App 窗口** → 键盘不在 XML 里。
2. **App 窗口不收缩**（本环境 `adjustPan`）→ 元素 bounds 不变。
3. **`screencap` 捕获整个屏幕** → 键盘在截图里。

于是：**截图说那里有键盘，XML 说那里有可点元素。**

---

## 4. 判定

### 4.1 盲区

XML 看不见的屏幕区域。当前只认定 IME：

```
blind = AccessibilityWindowInfo 中 type == TYPE_INPUT_METHOD (2) 的 bounds
```

> **C1**：识别盲区 必须 用 `type == TYPE_INPUT_METHOD`，
> 不得 用标题匹配（标题随输入法而变）。

> **C2**：**不得凭推测把其他窗口类型加入盲区。**
> toast、系统权限对话框、通知栏是否也在 XML 盲区里，**尚未验证**。
> 未验证的一律不进规范——这是为了不制造新的假判据。

### 4.2 幻影可点

```
phantom = XML 报 clickable=true 且 bounds 与盲区有重叠
```

### 4.3 截图验证

用截图**验证**盲区确实不是 App 内容。判据不是"颜色是什么"，
而是**盲区与 App 参考区域的像素统计不同**。

> **C3**：截图是参考通道，XML 是派生通道。
> 两者冲突时，**XML 错**。

> **C4**：没有截图时，`screenshot_agrees` 必须 报 None，
> 不得 假装验证过。

---

## 5. 参考实现

```python
from blindspot import cross_check, cross_check_from_files
import xml.etree.ElementTree as ET

r = cross_check_from_files("data/dump_before_tap.xml",
                           "data/windows_keyboard_up.json",
                           "data/screencap_keyboard_up.png")
# r["phantom_count"]   == 5
# r["phantom_ratio"]   ≈ 0.385
# r["screenshot_agrees"] == True
```

只有 XML + 窗口列表时：

```python
r = cross_check(ET.parse("dump.xml").getroot(), windows)
# r["phantom_count"]   == 5      ← IME bounds 精确，仍可判定
# r["screenshot_agrees"] is None ← 不假装验证过
```

---

## 6. 一致性条件

| # | 条件 |
|---|---|
| C1 | 识别盲区 必须 用 `type == TYPE_INPUT_METHOD`，不得 用标题匹配 |
| C2 | 不得 凭推测把未验证的窗口类型加入盲区 |
| C3 | 截图是参考通道；两者冲突时 XML 错 |
| C4 | 没有截图时 `screenshot_agrees` 必须 报 None |
| C5 | 判定重叠 必须 用面积，不得 用 y 坐标大小比较 |
| C6 | `parse_bounds` 必须 正确处理 `[x1,y1][x2,y2]` 内部的逗号 |
| C7 | 截图与 IME bounds 不一致时 必须 显式报告，不得 静默取其一 |

---

## 7. 边界

1. **取证来自一台 AVD、一个界面、一个输入法。**
   不同 ROM / 输入法 / `windowSoftInputMode` 会改变结论。
2. **只测了 `adjustPan`。** `adjustResize` 下窗口会缩小、bounds 会变，
   遮挡可能不出现，但 bounds 已变（uidref 的 `snapshot_id` 会变）。
3. **未验证：toast / 系统权限对话框 / 通知栏 / 音量面板**是否也在
   XML 盲区。**不得据本规范推断。**（见 C2）
4. **`screencap` 是否总是包含键盘，未在其它 ROM 上验证。**
5. **不处理"怎么把键盘收起来"。** `KEYCODE_BACK` 会同时触发返回逻辑。

---

## 8. 与其他库的关系

| 库 | 关系 |
|---|---|
| `imespec` | imespec 判"元素被键盘挡了多少"；blindspot 判"XML 根本不知道键盘存在" |
| `uidref` | uidref 给 ref；blindspot 判定哪些 ref 是**幻影** |
| `screenpoint` | screenpoint 做坐标数学；blindspot 判"这个坐标指向谁" |
| `devapi` | `/v1/act` 执行前 必须 排除幻影目标 |
| `screendiff` | ★ 本例中 screendiff 会看到"界面变了"——但那是键盘在响应，不是目标生效 |

**★ 与 screendiff 的关键交互**：blindspot 的失败模式会让 screendiff
看到一次变化。**"界面变了"不等于"我的动作生效了"。**
这是两个库必须配合使用的理由。

---

## 验证等级

本资产的量化声明在 **`docs/CLAIMS.md`**（`claimaudit/data/evidence_ledger.json`）登记，
含观测数 / 起始状态数 / 独立通道数 / 是否确定性 / 是否可引用。

复算：`python claimaudit/tools/audit_claims.py`

**规则**（来自 `claimcheck`）：单次观测只能产生假设，不能产生结论；
低于 V1 的声明不得作为结论引用；已推翻（V4）的声明必须留档并标注「不得作为结论」。

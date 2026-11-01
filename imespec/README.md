# imespec · 键盘遮挡与元素可及性判定

**[English](README.en.md)** · **[中文](README.md)**


**License** Apache-2.0 · **版本** 0.1.0 · **日期** 2026-10-27
**测试环境** AVD `avd-api35`（Android 15 / Google APIs / arm64-v8a）

---

> **English**
>
> Decide whether an element is actually reachable while the on-screen keyboard is up.
>
> The IME is a separate window that `uiautomator dump` never captures, and the app window does not shrink to make room for it.
>
> Verify: `./run-tests.sh`

## 一句话

**一个元素报着合法 `bounds` 和 `clickable=true`，点下去却命中键盘——
XML 不给任何信号。** 键盘弹起时实测 **38.5% 的可点元素点不到**。

---

## 核心证据

AVD Android 15，设置页搜索，输入 `net`，键盘弹起：

| | 值 |
|---|---|
| IME 窗口 | `type=2` `English (US) (QWERTY)`，bounds `0 1517 1080 2400` |
| 占屏幕 | **36.8%** |
| XML 节点数 | 35，package **全是** `com.google.android.settings.intelligence` |
| XML 里的键盘节点 | **0 个** |
| App 窗口 bounds | 仍是 `0 0 1080 2400`（**没收缩**） |
| 可点元素 | 13 |
| **完全遮挡** | **4** |
| **部分遮挡** | **1** |
| **不可及合计** | **5/13 = 38.5%** |

被完全压住的四个：`[0,1548][1080,1712]`、`[0,1712][1080,1935]`、
`[0,1935][1080,2158]`、`[0,2158][1080,2381]`。

agent 想点列表底部某一项（如 y≈2017 的"Allow WEP networks"），
点下去命中键盘。**没有异常、没有错误、点击"成功"了。**

---

## 根因

1. **IME 是独立窗口**（`TYPE_INPUT_METHOD`），
   `uiautomator dump` 只捕获**活动 App 窗口** → 键盘不在 XML 里。
2. **App 窗口不收缩**（本环境 `adjustPan`）→ 元素 bounds 不变，
   遮挡无从显现。

TalkBack 没这个问题，因为它跑在无障碍服务里，拿得到完整窗口列表。
基于 `uiautomator dump` 的 agent 拿不到。

---

## 判定

```
occlusion = overlap_area(element, ime) / area(element)
```

| 遮挡比 | 结论 |
|---|---|
| `== 0` | `reachable` |
| `(0, 1)` | `partially_occluded` |
| `>= 1` | `occluded` |

**★ 拿不到键盘信息时：`unknown`，不猜。**

猜"没键盘"→ agent 点空气；猜"有键盘"→ 正常场景下拒绝点击。
两个方向都会错，所以报 unknown。

---

## 参考实现

```python
from imespec import audit_xml, ime_from_windows, ime_rect
import xml.etree.ElementTree as ET

# 有窗口信息（无障碍服务）
wins = {"windows": [...]}                 # getWindows() 序列化
ime = ime_rect(ime_from_windows(wins["windows"]))
root = ET.parse("dump.xml").getroot()
r = audit_xml(root, ime)
# r["unreachable_count"] == 5, r["unreachable_ratio"] ≈ 0.385

# 只有 XML
r = audit_xml(root, None)
# r["ime_known"] == False
# r["items"][i]["reachability"] == "unknown"     ← 不猜
```

---

## 怎么拿到键盘信息

| 途径 | 能否判定 | 说明 |
|---|---|---|
| `AccessibilityWindowInfo` | ✅ | 需无障碍权限；`uidref` 读取侧已在用同一把钥匙 |
| `dumpsys input_method` | ✅ | **调试命令，非公开 API**，不得进生产路径 |
| `uiautomator dump` XML | ❌ | 键盘不在 XML 里 |

### 一个负发现

`AccessibilityService` **没有** IME 状态访问器。
`InputMethodManager.isAcceptingText()` 不在该服务可用 API 里
（API 33+ 已 deprecated）。**公开无障碍 API 不提供"键盘是否弹出"的
直接查询**，只能通过窗口列表间接得到。

这条负发现记录在 `textin/refapp` 的 `reportWindows()` 注释里。

---

## 识别 IME：用 type，不用标题

标题是输入法名字（`English (US) (QWERTY)` / `简体中文拼音`），
随用户装的输入法而变。**判据是 `type == TYPE_INPUT_METHOD (2)`。**

黄金向量 `ime-title-localized` 专门测这件事：标题换成中文输入法，
识别结果不变。

---

## 目录

```
imespec/
├── SPEC.md                 规范：证据 + 判定 + 一致性条件 C1–C6
├── README.md               本文件
├── core.py                 参考实现
├── vectors.py              黄金向量（bounds / 遮挡 / unknown / 窗口识别）
├── vectors_lib.py          测试辅助
├── tests/                  37 条 pytest（含真机证据复算）
├── tools/
│   └── probe_ime.py        真机探针：抓两份 + 复算 + 存证
└── data/
    ├── dump_keyboard_up.xml       真机 dump（键盘弹起）
    ├── windows_keyboard_up.json   真机窗口列表（含 IME）
    └── dump_no_keyboard.xml       对照（键盘收起）
```

## 测试

```bash
cd imespec
python -m pytest tests/ -q          # 37 passed
python tools/probe_ime.py            # 真机：键盘弹起
python tools/probe_ime.py --no-keyboard   # 真机：键盘收起（对照）
```

`TestRealEvidence` 从 `data/` 的真机 dump **复算**，
验证规范与实现一致（4 个完全遮挡、1 个部分遮挡、5/13 不可及）。
**这是防回归的锚**：将来改坏判定逻辑，这里会红。

---

## 边界

1. **取证来自一台 AVD、一个界面、一个输入法。** 不同 ROM / 输入法 /
   `windowSoftInputMode`（`adjustResize`/`adjustPan`/`adjustNothing`）
   会改变结论。**换设备需重跑 `tools/probe_ime.py`。**
2. **只测了 `adjustPan`。** 若 App 用 `adjustResize`，窗口会缩小、
   bounds 会变——遮挡可能不出现，但 bounds 已变，那是另一类问题
   （uidref 的 `snapshot_id` 会变）。
3. **多窗口 / 分屏 / 画中画未测。**
4. **本规范不处理"怎么把键盘收起来"**——那属于 act 侧，且
   `KEYCODE_BACK` 会同时触发返回逻辑，副作用不在范围内。

---

## 与其他库的关系

| 库 | 关系 |
|---|---|
| `uidref` | uidref 给 ref；imespec 给这些 ref 的**可及性** |
| `fieldstate` | fieldstate 判"字段能否写"；imespec 判"点了会不会命中键盘" |
| `textin` | textin 判"文本怎么送进去"；imespec 判"送进去之后 UI 变成什么样" |
| `devapi` | `/v1/act` 执行前应查可及性 |

**imespec 是横切关注点**：它不产出新能力，只是让已有的点击能力
**不说谎**。

---

## 适用范围

**本库定位**：Apache-2.0，无第三方应用依赖，命名中性。
核心证据是可复现的真机事实（38.5% 不可及、XML 无键盘节点、
App 窗口不收缩），不是观点。

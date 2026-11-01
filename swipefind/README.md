# swipefind · 滚动手势的有效性与吸收判定

**[English](README.en.md)** · **[中文](README.md)**


**License** Apache-2.0 · **版本** 0.1.0 · **日期** 2026-10-27
**测试环境** AVD `avd-api35`（Android 15 / Google APIs / arm64-v8a）

---

> **English**
>
> Validity and absorption rules for swipe gestures.
>
> A swipe that starts on the keyboard writes into the focused field instead of scrolling, and the working distance range is not monotonic.
>
> Verify: `./run-tests.sh`

## 一句话

**`input swipe` 返回成功、退出码 0，但可能什么都没滚——
或者滚了，同时往你的输入框里写了三个字。**

---

## ★★ 核心证据一：键盘区起滑会被吸收并写入文本

设置页搜索输入 `net`，键盘弹起：

| 手势 | 字段变化 |
|---|---|
| 键盘区垂直上滑 (540,2000)→(540,1000) | `net` → **`net by`** |
| 键盘区斜滑 (700,2100)→(380,1200) | `net` → **`net be`** |
| 键盘区短滑 (540,1900)→(540,1600) | `net` → **`net gt`** |
| **对照 · App 区滑动** (540,1400)→(540,400) | `net` → `net` ✅ |

**一次滚动手势，静默往输入框写入 2–3 个字符。**

这是 `blindspot` tap 发现的手势版，但更糟：tap 写一个字符，
**swipe 写多个**。

---

## ★ 核心证据二：距离非单调

固定 250ms，只改距离：

| 距离 | 结果 |
|---|---|
| 100px | ❌ |
| 300px | ❌ |
| 600px | ✅ |
| 900px | ✅ |
| **1200px** | **❌** |
| **1500px** | **❌** |

**不是"越长越好"。** 有一个甜点区，超过它同样静默失败。

---

## 判定

```python
from swipefind import (absorbed_by_keyboard, gesture_length,
                       is_exhausted, likely_effective)

likely_effective(600, 250)    # 'likely'
likely_effective(1500, 250)   # 'unlikely'   ← 太长也不行

absorbed_by_keyboard(540, 2000, 540, 1000, ime)["absorbed"]   # True
absorbed_by_keyboard(540, 1400, 540, 400, ime)["absorbed"]    # False

is_exhausted([{"new": 9, "gone": 6},
              {"new": 0, "gone": 0},
              {"new": 0, "gone": 0}])                          # True
```

**吸收判据是起点在键盘内，不是路径相交。**
**路径相交必须用线段-矩形相交，不能用端点包围盒**——
垂直滑动的包围盒是零宽矩形，重叠恒为 0。

---

## ★ 一个方法论坑

`am start -a android.settings.SETTINGS` + `KEYCODE_BACK`
**不是可靠复位**——它不重置滚动位置。

它让我得出两个错误结论：
- "200ms 以下完全无效"（阈值假象）
- "滚过头不可恢复，restored = 0/6"

改用 HOME 键复位后：200ms 有效，下滚 3 + 上滚 3 恢复 18/22。

> **复位本身也要有判据。否则装置的失败会被当成被测对象的失败。**

---

## 目录

```
swipefind/
├── SPEC.md      规范：证据 + 判定 + 一致性条件 C1–C6
├── README.md    本文件
├── core.py      参考实现
├── vectors.py   黄金向量（bounds / 长度 / 吸收 / 终止 / 恢复）
├── tests/       50 条 pytest（含向量非空转元测试）
├── tools/
│   ├── probe_swipe.py          时长 + 终止 + 过头
│   ├── probe_overshoot.py      验证"不可恢复"是否为假象
│   ├── probe_threshold.py      阈值 + 距离依赖 + 键盘区起点
│   ├── probe_5c_mechanism.py   5C 机制判别
│   └── probe_kb_swipe.py       键盘吸收干净复现（3/3）
└── data/
    ├── swipe_experiments.json  六个实验的原始观测
    └── keyboard_swipe.json     键盘吸收 3/3 复现
```

## 测试

```bash
cd swipefind
python -m pytest tests/ -q      # 50 passed
```

---

## 边界

1. **一台 AVD、一个列表、垂直方向、250ms。** 甜点区数值换设备需重测。
2. **水平滚动、多指、`input roll`、`input draganddrop` 未测。**
3. **`adjustResize` 未测。**
4. **不处理"怎么把键盘收起来"。**

---

## 与其他库的关系

| 库 | 关系 |
|---|---|
| `blindspot` | blindspot 判"点下去命中谁"；swipefind 判"滑下去命中谁" |
| `fieldstate` | ★ swipefind 的失败会**污染输入框**——正好落在 fieldstate 管界 |
| `agentloop` | agentloop S2 的"11/14 步无效上滑"，机制在本库有解 |
| `devapi` | `/v1/act` 的 swipe 端点应先过 `absorbed_by_keyboard` |

---

## 适用范围

**本库定位**：Apache-2.0，命名中性，无第三方应用依赖。
核心证据是可复现的真机事实（3/3 键盘吸收、距离非单调、18/22 可恢复），
且包含一条对自己不利的方法论坑（`reset_home()` 污染了两个实验）。

---

## 验证等级

本资产的量化声明在 **`docs/CLAIMS.md`**（`claimaudit/data/evidence_ledger.json`）登记。

复算：`python claimaudit/tools/audit_claims.py`

**规则**（来自 `claimcheck`）：单次观测只能产生假设，不能产生结论；
低于 V1 不得作为结论引用；已推翻（V4）必须留档并标注「不得作为结论」。

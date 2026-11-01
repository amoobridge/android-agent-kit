# blindspot · XML dump 的非 App 窗口盲区

**License** Apache-2.0 · **版本** 0.1.0 · **日期** 2026-10-27
**测试环境** AVD `avd-api35`（Android 15 / Google APIs / arm64-v8a）

---

## 一句话

**agent 有两条感知通道，它们对"屏幕上有什么"给出不一致的答案。**
截图包含键盘，XML 完全看不见键盘——于是 **38.5% 的 XML 可点元素是幻影**。

---

## 核心证据

AVD Android 15，设置页搜索输入 `net`，键盘弹起：

| | 截图 `screencap` | XML `uiautomator dump` |
|---|---|---|
| 尺寸 | 1080×2400 | 35 节点 |
| 键盘 | **有**，y≥1517 | **零个节点** |
| 键盘起点 | y=1517 | — |
| 与 IME bounds 一致性 | **精确相等** | — |
| App 窗口 | — | 仍是 `0 0 1080 2400`（没收缩） |

键盘边界的截图证据（逐行取色）：

```
y=1500  rgb(232,231,239)   ← App 背景
y=1509  rgb(231,230,238)   ┐
  ...  （16 像素渐变）      │ 阴影
y=1516  rgb(223,222,230)   ┘
y=1517  rgb(241,240,247)   ← 键盘背景（比 App 亮）
y=1600  rgb(241,240,247) + rgb(176,198,255) + rgb(255,255,255)  ← 按键
```

**截图里 y=1517 起就是键盘，与 `AccessibilityWindowInfo` 报的
`0 1517 1080 2400` 精确相等。**

---

## ★★ 行为后果（决定性证据）

```
状态     搜索框 text
点击前   "net"
点击后   "netv"      ← 点了 XML 说 clickable=true 的 [0,1935][1080,2158]
```

点击坐标 (540, 2017) 落在键盘的 `v` 键上。
**agent 的点击被键盘接收，并向 App 写入了它没打算写入的数据。**

这不只是"没反应"，是**静默的状态污染**。

而且：如果 agent 只比较"界面是否变化"，它会看到变化
（搜索框内容变了），**可能误判为点击生效**。

---

## 38.5% 是幻影

XML 报 `clickable=true` 的 13 个节点：

| bounds | 遮挡比 |
|---|---|
| `[0,1384][1080,1548]` | 18.9% |
| `[0,1548][1080,1712]` | **100%** |
| `[0,1712][1080,1935]` | **100%** |
| `[0,1935][1080,2158]` | **100%** |
| `[0,2158][1080,2381]` | **100%** |

**5/13 = 38.5% 不可及。**

---

## 判定

```
blind    = AccessibilityWindowInfo 中 type == TYPE_INPUT_METHOD (2) 的 bounds
phantom  = XML 报 clickable=true 且 bounds 与 blind 有重叠
```

**截图是参考通道，XML 是派生通道。两者冲突时，XML 错。**

**没有截图时 `screenshot_agrees` 报 None，不假装验证过。**

---

## 参考实现

```python
from blindspot import cross_check_from_files

r = cross_check_from_files("data/dump_before_tap.xml",
                           "data/windows_keyboard_up.json",
                           "data/screencap_keyboard_up.png")
# r["phantom_count"]     == 5
# r["phantom_ratio"]     ≈ 0.385
# r["screenshot_agrees"] == True
```

---

## 目录

```
blindspot/
├── SPEC.md      规范：证据 + 判定 + 一致性条件 C1–C7
├── README.md    本文件
├── core.py      参考实现
├── vectors.py   黄金向量（bounds / 盲区识别 / 幻影）
├── vectors_lib.py
├── tests/       37 条 pytest（含真机证据复算）
├── tools/
│   └── probe_dualview.py   真机探针，可 --tap-phantom 做行为验证
└── data/
    ├── screencap_keyboard_up.png   真机截图（含键盘）
    ├── dump_before_tap.xml         真机 XML（无键盘）
    ├── windows_keyboard_up.json    真机窗口列表（含 IME）
    ├── dump_after_tap.xml          点击幻影后的 XML
    └── behavioral_evidence.json    行为证据 net → netv
```

## 测试

```bash
cd blindspot
python -m pytest tests/ -q                          # 37 passed
python tools/probe_dualview.py                      # 真机复算
python tools/probe_dualview.py --tap-phantom        # 真机行为验证
```

---

## 边界

1. **一台 AVD、一个界面、一个输入法。** 换设备需重跑探针。
2. **只测了 `adjustPan`。** `adjustResize` 下窗口会缩小、bounds 会变。
3. **未验证：toast / 系统权限对话框 / 通知栏 / 音量面板**是否也在
   XML 盲区。**不得据本规范推断**（C2 明令禁止凭推测加入）。
4. **`screencap` 是否总是包含键盘，未在其它 ROM 验证。**

---

## 与其他库的关系

| 库 | 关系 |
|---|---|
| `imespec` | imespec 判"元素被键盘挡了多少"；blindspot 判"XML 根本不知道键盘存在" |
| `uidref` | uidref 给 ref；blindspot 判定哪些 ref 是**幻影** |
| `devapi` | `/v1/act` 执行前 必须 排除幻影目标 |
| `screendiff` | ★ blindspot 的失败模式会让 screendiff 看到"界面变了"——**但那是键盘在响应，不是目标生效** |

**★ 与 screendiff 的关键交互**：`界面变了` ≠ `我的动作生效了`。
这是两个库必须配合使用的理由。

---

## 适用范围

**本库定位**：Apache-2.0，无第三方应用依赖，命名中性。
核心证据是可复现的真机事实（截图含键盘、XML 不含、38.5% 幻影、
点击导致 net→netv），不是观点。

---

## 验证等级

本资产的量化声明在 **`docs/CLAIMS.md`**（`claimaudit/data/evidence_ledger.json`）登记。

复算：`python claimaudit/tools/audit_claims.py`

**规则**（来自 `claimcheck`）：单次观测只能产生假设，不能产生结论；
低于 V1 不得作为结论引用；已推翻（V4）必须留档并标注「不得作为结论」。

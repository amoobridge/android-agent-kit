# capturetrap · `uiautomator dump` 抓取层的四个陷阱

**License** Apache-2.0 · **版本** 0.1.0 · **日期** 2026-10-27
**测试环境** AVD `avd-api35`（Android 15 / Google APIs / arm64-v8a）

---

> **English**
>
> Four silent traps in the `uiautomator dump` capture layer.
>
> All four surface as "no data returned" rather than as errors, so they get mistaken for a broken device.
>
> Verify: `./run-tests.sh`

## 一句话

**你的观测装置会静默失效，而失效看起来像"设备没返回数据"。**

本项目此前 14 个库都靠同一行命令拿界面结构。本库记录这行命令自身的陷阱。

---

## ★★ 我自己的探针连续中了三个

| 陷阱 | 症状 | 为什么难发现 |
|---|---|---|
| `adb uiautomator` | `adb: unknown command uiautomator` | returncode 1 被忽略 → 文件不存在 → cat 报错 → 上层得到 `(empty)` |
| `text=True` | `UnicodeDecodeError: byte 0xb5` | 崩在抓取阶段，看起来像"设备连不上" |
| `startswith("<hierarchy")` | 抓取函数**恒返回 None** | 输出以 `<?xml` 声明开头，`<hierarchy` 在声明之后 |

**三个都表现为"拿不到数据"，没有一个报出"你写错了"。**

---

## ★ 陷阱四：原地覆写

`uiautomator dump` 原地覆写同一个文件。读到上一份内容时，
**旧文件同样是合法 XML、判定照样通过**。

观测：切换屏幕后连续 5 次 `dump + cat`，md5 全部相同。

**这一条我没完全排除"屏幕真的没变"**，已用截图交叉验证过一次。

---

## ★ 一个未复现的假设（明确留档）

我一度以为发现了「`am start` 是恢复原语，不 force-stop 会停在上次页面」——
三种命令不 force-stop 全落错、force-stop 后全落对，看起来非常像发现。

**复现检查推翻了他**：换了个起始状态，不 force-stop 也全部落对。

> **假设不成立，不得作为结论提交。**
> 原始观测和复现结果都留在 `data/nav_experiments.json`——
> 它记录了一次"看起来很像发现"的东西如何被复现检查推翻。

---

## 正确的抓取函数

```python
# C4 先删，避免读到上一份
run(adb, dev, "shell", "rm", "-f", remote)
# C1 uiautomator 是设备侧命令，必须经 shell；且检查返回码
rc, _, err = run(adb, dev, "shell", "uiautomator",
                 "dump", "--compressed", remote)
if rc != 0: raise RuntimeError(f"dump 失败: {err}")
# C2 二进制读   C3 find 而非 startswith
raw = run_bytes(adb, dev, "exec-out", "cat", remote)
if raw[:200].find(b"<hierarchy") >= 0:
    return ET.fromstring(raw.decode("utf-8", "replace"))
```

---

## 目录

```
capturetrap/
├── SPEC.md      规范：四陷阱 + 未复现假设留档 + 一致性条件 C1–C4
├── README.md    本文件
├── core.py      参考实现
├── vectors.py   黄金向量
├── tests/       pytest
├── tools/
│   ├── probe_nav_unreproduced.py   导航假设探针（未复现，留档）
│   └── probe_capture.py            抓取陷阱复现探针
└── data/
    └── nav_experiments.json        首次观测 + 复现结果 + 结论
```

---

## 边界

1. 一台 AVD、一个 adb 版本。
2. 陷阱四未完全排除"屏幕真的没变"。
3. 未测：不带 `--compressed`、dump 到 `/sdcard`、`adb shell` 的 LF/CRLF。

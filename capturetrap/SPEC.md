# capturetrap 规范 · `uiautomator dump` 抓取层的四个陷阱

**版本** 0.1.0 · **日期** 2026-10-27 · **License** Apache-2.0
**测试环境** AVD `avd-api35`（Android 15 / Google APIs / arm64-v8a），emulator-5554

---

## 0. 这个库是什么

本项目此前所有库（uidref / screendiff / scrollkey / crosstrack / blindspot /
imespec / fieldstate / textin / screenpoint / pointparse / agentloop /
devapi / swipefind）都靠同一行命令拿界面结构：

```
adb shell uiautomator dump --compressed <remote>
adb exec-out cat <remote>
```

本库记录这行命令**自身的四个陷阱**。它们不是被测 App 的问题，
是**观测装置**的问题——而装置的失败会被当成被测对象的失败。

> 已经记录过两个（异步落盘、OOM Kill）。
> 本库补另外四个，其中**两个是装置 bug、一个是判据 bug**，
> **一个假设未复现、明确留档**。

---

## 1. 四个陷阱

### 1.1 ★★ 陷阱一：`adb uiautomator` 是「未知命令」

```python
subprocess.run([ADB, "-s", DEV, "uiautomator", "dump", ...])
# → adb: unknown command uiautomator     （stderr）
# → returncode = 1                        （被忽略）
# → 远端文件不存在                        （cat 报 No such file）
# → 上层静默得到空界面
```

`uiautomator` 是**设备侧 shell 命令**，必须经 `adb shell`。
写成 `adb uiautomator` 时 adb 自己报错，**不是设备报错**。

**危害**：我自己的探针因此连续输出 `(empty)` 而不报错。
如果没去查 returncode，会以为"设备返回了空界面"。

> **C1**：所有 adb 调用 必须 检查 returncode 与 stderr。
> 忽略返回码会让"命令根本没执行"和"执行了但结果为空"无法区分。

### 1.2 ★★ 陷阱二：`text=True` 撞上非 UTF-8 字节

```python
subprocess.run([...], capture_output=True, text=True)
# → UnicodeDecodeError: 'utf-8' codec can't decode byte 0xb5
#   in position 262: invalid start byte
```

`dumpsys` 输出含非 UTF-8 字节。**整个实验直接崩掉**，
而它崩在抓取阶段，看起来像"设备连不上"。

> **C2**：读 adb 输出 必须 用二进制 + `decode("utf-8", "replace")`，
> 不得 用 `text=True`（默认 strict）。

### 1.3 ★ 陷阱三：输出以 `<?xml` 声明开头，不是 `<hierarchy`

```python
out.lstrip().startswith("<hierarchy")     # ← 恒为 False
raw[:200].find(b"<hierarchy") >= 0        # ← 正确
```

`uiautomator dump` 的输出是：

```
<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation="0">
```

`<hierarchy` 在 XML 声明**之后**。用 `startswith` 判会让抓取函数
永远返回 None——**而这是一个静默失效的判据**（函数返回 None，
调用方只会看到"没抓到"，不会看到"判据写错了"）。

> **C3**：抓取有效性判据 必须 用 `find(...) >= 0` 或剥掉 XML 声明，
> 不得 用 `startswith("<hierarchy")`。

### 1.4 ★ 陷阱四：原地覆写导致读到上一份内容

`uiautomator dump` **原地覆写**同一个远端文件。读的时候可能拿到
上一份内容，而**旧文件同样是合法 XML、前 200 字节判定照样通过**。

我观测到：切换屏幕后连续 5 次 `dump + cat`，md5 全部相同
（`fb029f35d3bae2ffc953f1ead999cb50`），`rm -f` 之后仍然相同。

> **C4**：dump 之前 必须 `rm -f` 远端文件；
> 且 必须 用内容签名判定"这次抓的是不是新内容"，
> 不能只判"是不是合法 XML"。

**注意**：这一条我**没有完全排除**是"屏幕真的没变"。
已用截图交叉验证过一次（截图与 XML 一致），
但那是单次观测，**不构成充分证据**。

---

## 2. 一个未复现的假设（明确留档，不得当作结论）

**假设**：`am start` 是恢复原语；不 `force-stop` 时会停在上次页面。

**首次观测**（设备停在 Connected devices）：

| 命令 | 不 force-stop | force-stop 后 |
|---|---|---|
| `am start -a android.settings.SETTINGS` | Connected devices ❌ | Settings ✅ |
| `am start -a android.settings.WIFI_SETTINGS` | Android Auto ❌ | T-Mobile ✅ |
| `am start -n .../.wifi.WifiSettings` | Connected devices ❌ | Wi-Fi ✅（3/3） |

**复现尝试**：先打开 Wi-Fi 设置，再连续三次 `am start -a android.settings.SETTINGS`

| 条件 | 结果 |
|---|---|
| 不 force-stop | Settings / Search settings ✅✅✅ |
| force-stop 后 | Settings / Search settings ✅✅✅ |

**★ 未复现。** 两种情况下都正确落到 Settings 主页。

**结论**：假设不成立，或仅在特定设备状态下成立。
**不得作为结论提交。** 原始观测与复现结果都留在
`data/nav_experiments.json`，因为它记录了一次"看起来很像发现"的东西
如何被复现检查推翻。

---

## 3. 抓取函数的正确形态

```python
def capture(adb, dev, remote):
    """★ 四个陷阱全部规避过的抓取函数。"""
    # C4：先删，避免读到上一份
    run(adb, dev, "shell", "rm", "-f", remote)
    # C1：uiautomator 是设备侧命令，必须经 shell；且检查返回码
    rc, _, err = run(adb, dev, "shell", "uiautomator",
                     "dump", "--compressed", remote)
    if rc != 0:
        raise RuntimeError(f"dump 失败: {err}")
    for _ in range(8):
        time.sleep(0.3)
        # C2：二进制读，不抛 UnicodeDecodeError
        raw = run_bytes(adb, dev, "exec-out", "cat", remote)
        # C3：find 而非 startswith（输出以 <?xml 开头）
        if raw[:200].find(b"<hierarchy") >= 0:
            return ET.fromstring(raw.decode("utf-8", "replace"))
    raise RuntimeError("dump 超时")
```

---

## 4. 一致性条件

| # | 条件 |
|---|---|
| C1 | 所有 adb 调用 必须 检查 returncode 与 stderr |
| C2 | 读 adb 输出 必须 二进制 + `decode("utf-8","replace")` |
| C3 | 有效性判据 必须 用 `find(...) >= 0`，不得 用 `startswith("<hierarchy")` |
| C4 | dump 前 必须 `rm -f` 远端文件；必须 用内容签名判新 |

---

## 5. 边界

1. **一台 AVD、一个 adb 版本。** 换设备/换 adb 版本需重跑探针。
2. **陷阱四未完全排除**"屏幕真的没变"这一解释，已用截图交叉验证过一次。
3. **未测**：`uiautomator dump` 不带 `--compressed`、dump 到 `/sdcard`、
   以及 `adb shell` 的 LF/CRLF 转换（已证本环境无此现象）。

---

## 6. 与其他库的关系

本库是**所有其他库的地基**。已把前两个坑回写进 uidref / agentloop /
devapi；本库的四个坑同样适用，且**抓取函数自己就中过三个**
（`adb uiautomator`、`text=True`、`startswith`）——
三个都发生在同一个探针里，且都表现为"拿不到数据"而不是"报错"。

---

## 验证等级

本资产的量化声明在 **`docs/CLAIMS.md`**（`claimaudit/data/evidence_ledger.json`）登记，
含观测数 / 起始状态数 / 独立通道数 / 是否确定性 / 是否可引用。

复算：`python claimaudit/tools/audit_claims.py`

**规则**（来自 `claimcheck`）：单次观测只能产生假设，不能产生结论；
低于 V1 的声明不得作为结论引用；已推翻（V4）的声明必须留档并标注「不得作为结论」。

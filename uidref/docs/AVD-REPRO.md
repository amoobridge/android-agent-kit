# AVD 复现手册 · `uiautomator dump` 的四个坑

**环境**：AVD `avd-api35`（Android 15 / Google APIs / arm64-v8a）
· adb 1.0.41 · 本机 macOS
**日期**：2026-10-27 · **License** Apache-2.0

> 这份手册的目的：让任何人在自己的设备上**独立复现**下面四条，
> 而不是只能选择相信本文档。

---

## 0. 先说最重要的：四条里只有一条必现

我把四条按**可复现性**分了类。这个分类比"四条都是坑"更诚实，
也更经得起审查：

| # | 坑 | 类型 | 本环境可复现？ | 证据 |
|---|---|---|---|---|
| 1 | 异步落盘 | **负载依赖** | ❌ 当前不可复现 | 5 次实测，命令返回 1.95s 后文件立即可读 |
| 2 | 裸 dump 被 OOM Kill | **负载依赖** | ❌ 当前不可复现 | 3 次对照，MemFree ≈ OOM 时但 load 低，裸 dump 全成功 |
| 3 | dump 路径在设备上解释 | **确定性** | ✅ **必现** | `../tools/diagnose_dump.py` 最后一项 |
| 4 | `shell cat` 的 CRLF | **未复现** | ❌ 无法复现 | 两种读法字节相同，且 XML 是单行 |

**由此得出的保留防御代码的理由**（这是本文档的核心论点）：

> 坑 1、2、4 的防御代码**不是**因为在本环境验证过才留下的，
> 而是因为它们**负载/版本依赖**——在别的设备、别的 adb 版本、
> 别的内存压力下可能现形。坑 3 是确定性的，任何时候都会现形。

把"我验过了"和"我防着"分开说，是这份手册唯一重要的事。

---

## 1. 一键诊断

```bash
python tools/diagnose_dump.py --device emulator-5554
```

8 项检查，每项 PASS / FAIL / WARN / INFO + 可执行建议。

---

## 坑 1 · 异步落盘（负载依赖，当前不可复现）

### 声称的现象

`uiautomator dump` 命令**已经返回成功**，但紧接着 `cat` 读到空串。

### 实测：当前环境不现形

连续 5 次，测「dump 命令返回后，文件是否立即可读」：

```
trial0: 命令返回 1.95s · 立即读 OK (1.97s) · 轮询补等 0.0s · 5408B
trial1: 命令返回 1.94s · 立即读 OK (1.97s) · 轮询补等 0.0s · 5408B
trial2: 命令返回 1.95s · 立即读 OK (1.98s) · 轮询补等 0.0s · 5408B
trial3: 命令返回 1.94s · 立即读 OK (1.97s) · 轮询补等 0.0s · 5408B
trial4: 命令返回 1.95s · 立即读 OK (1.97s) · 轮询补等 0.0s · 5408B
```

**`uiautomator dump` 本身要花约 1.95 秒**（不是"瞬间返回"），
返回时文件已经写完了。

### 那为什么还要轮询？

因为**这是负载依赖的**：设备繁忙时 dump 可能在更早阶段就返回。
`1.95s` 是闲时数字，忙时可能短得多。

**轮询的代价极低**（闲时第一次就读到，0 次额外等待），
**不轮询的代价是忙时静默拿到空串**。这个不对称性决定了要防。

### 处理

轮询等 `<hierarchy` 出现，而不是读一次就放弃。参考实现见
`http_api.capture_via_adb()` 与 `agentloop/device.py::dump_xml()`。

---

## 坑 2 · 裸 dump 被 OOM Kill ★最难发现（负载依赖）

### 声称的现象

```
$ adb -s emulator-5554 shell uiautomator dump /sdcard/t.xml
Killed
$ adb -s emulator-5554 shell ls -la /sdcard/t.xml
No such file or directory
```

**三个特征叠在一起，所以极难定位**：
1. 不产生文件
2. 退出码不报错（`Killed` 只是 stdout 里的一行文本）
3. 上层只看到"轮询 N 次都没等到 XML"，完全看不出是内存问题

### ★ 实测三次对照：MemFree 不是判据，load 才是

| 时刻 | MemFree | MemAvailable | load(1min) | 裸 dump | `--compressed` |
|---|---|---|---|---|---|
| 17:29 | 207 MB | 1149 MB | **5.40** | ❌ Killed | ✅ 11226 B |
| 17:48 | 266 MB | 1197 MB | **0.06** | ✅ 13077 B | ✅ 5404 B |
| 21:15 | 234 MB | 1164 MB | **0.19** | ✅ 13081 B | ✅ 5408 B |

**MemFree 三次几乎一样（207 / 266 / 234 MB），结果却不同。**
真正的判据是 **load average**——load 高说明 CPU/IO 饱和，
dump 要遍历整棵视图树又吃内存，这时才容易被 Kill。

> 这是我在 修正过的一个错误判据。`../tools/diagnose_dump.py` 的内存检查
> 因此改成 **load ≥ 1.0 才 WARN**，MemFree 偏低但 load 低时明确说明
> "实测此状态下裸 dump 仍能成功"。

### 复现（如果 load 已经降下来了）

OOM 需要内存/CPU 压力，不能凭空造。可行的加压方式：

```bash
# 方式一：并发反复 dump，把 load 顶上去
for i in $(seq 1 30); do
  adb -s emulator-5554 shell uiautomator dump /sdcard/stress.xml &
done; wait

# 方式二：长时间挂着 AVD（本文档作者是跑了 6 小时后自然进入该状态）
uptime   # 看 load average
```

### 处理

**顺序必须是先压缩、后普通**——不是反过来：

```python
for extra in (["--compressed"], []):
    ...
```

压缩版内存减半、文件也减半（13KB → 5.4KB）。

> ⚠️ **如果你复现不出来**：不代表这个坑不存在，只代表你的设备当前
> 不在内存压力状态。`../tools/diagnose_dump.py` 会把 load 和 MemFree 一起报给你。

---

## 坑 3 · dump 路径在设备上解释 ★唯一确定性可复现

### 现象

dump 永远写不进去，轮询全部超时。**不报错。**

### 复现（必现）

```bash
adb -s emulator-5554 shell uiautomator dump /var/folders/zz/not_on_device.xml
adb -s emulator-5554 exec-out cat /var/folders/zz/not_on_device.xml
# → cat: ... No such file or directory
```

`/var/folders/...` 是 **macOS host** 的临时目录。`adb shell` 里的路径
在**设备上**解释，所以设备上当然找不到它。

### 根因（这是我最容易犯的错）

Python 的 `tempfile.mktemp()` 返回的是 host 路径。把它直接传给
`adb shell uiautomator dump <path>` 就踩坑。

### 处理

远端路径一律用设备侧路径：`/data/local/tmp/...` 或 `/sdcard/...`。

`../tools/diagnose_dump.py` 最后一项专门验这个。

---

## 坑 4 · `adb shell cat` 的 CRLF ★本机未能复现

### 声称的现象

`adb shell cat` 走 pty，可能把 LF 转成 CRLF，污染 XML。

### 实测结论：**不成立**

```bash
$ adb -s emulator-5554 shell "printf 'a\nb\nc\n' > /data/local/tmp/p.txt"
$ adb -s emulator-5554 shell     cat /data/local/tmp/p.txt | xxd
00000000: 610a 620a 630a              a.b.c.        ← 纯 LF
$ adb -s emulator-5554 exec-out  cat /data/local/tmp/p.txt | xxd
00000000: 610a 620a 630a              a.b.c.        ← 完全相同
```

**两种读法字节完全一样。** 而且 `uiautomator dump` 产出的 XML 是
**单行、0 个换行符**：

```bash
$ adb -s emulator-5554 exec-out cat <dump.xml> | tr -cd '\n' | wc -c
0
```

### 诚实的结论

这条坑在当前环境（adb 1.0.41 + Android 15）**无从显现**：
- `shell cat` 不加 CRLF
- XML 本身没有换行符可被转换

**所以 uidref README / agentloop README / SPEC 里原来的
"shell 会把 LF 转 CRLF，污染 XML"是过度断言。** 已改为：

> `exec-out` 仍是更稳的选择（它语义上就是原始字节流、不依赖 pty 行为），
> 但**不是**因为在本环境实测到了 CRLF 污染。

**保留 `exec-out` 的理由**：它语义上就是"原始字节流"，不依赖 pty 行为；
这是防御性的正确选择，只是不该用一个没验证过的现象来论证它。

### 如果你复现出了 CRLF

请在 issue 里附上：adb 版本、设备/ROM、`xxd` 输出。有了证据我再把这条
从"声称"升级为"已验证"。

---

## 附：本手册的测试

`uidref/tests/test_capture_fallback.py` 5 条，用假 adb 覆盖：

| 测试 | 守什么 |
|---|---|
| `test_compressed_succeeds_first` | 第一次必须带 `--compressed` |
| `test_falls_back_when_compressed_oom_killed` | 压缩失败必须回退普通版 |
| `test_both_fail_error_mentions_memory` | 错误信息要提示可能是内存不足 |
| `test_remote_path_is_device_path` | 远端路径必须是设备侧路径 |
| `test_uses_exec_out_not_shell_for_read` | 读文件走 `exec-out` |

**这些测试做过变异敏感性验证**：用 之前的旧实现跑同一个假 adb，
得到 `RuntimeError: adb dump 失败`——旧实现拿不到 XML、新的能拿到。
测试真的在保护这条修复，不是空转。

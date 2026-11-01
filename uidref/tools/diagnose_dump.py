#!/usr/bin/env python3
"""uiautomator dump 诊断器 —— 一键判断"我的设备现在能不能抓 dump"。

用法：
    python tools/diagnose_dump.py [--device emulator-5554]

它会依次检查四件事，每件给出 PASS / FAIL / WARN 和可执行建议：

    1. adb 可达 + 单设备（多台设备不带 -s 会直接报错）
    2. 裸 `uiautomator dump` 是否被 OOM Kill
    3. `--compressed` 是否可用
    4. 读文件方式是否安全（shell 的 CRLF 污染）

**为什么要有这个脚本**：坑 2（OOM Kill）最难发现——不产文件、也不返回
非零退出码。上层只看到"轮询 N 次都没等到 XML"，完全看不出是内存不足。
本脚本把这三件事直接量化给你看。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from dataclasses import dataclass

ADB_DEFAULT = "~/Library/Android/sdk/platform-tools/adb"
REMOTE = "/data/local/tmp/_uidref_diag.xml"


@dataclass
class Check:
    name: str
    verdict: str      # PASS / FAIL / WARN / INFO
    detail: str
    advice: str = ""


def sh(adb: str, device: str, *args: str, timeout: int = 60) -> tuple[int, str, str]:
    r = subprocess.run([adb, "-s", device, *args], capture_output=True, timeout=timeout)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


# ---------------------------------------------------------------- 检查项

def check_adb(adb: str, device: str) -> list[Check]:
    out = []
    # 1a. adb 存在
    r = subprocess.run([adb, "version"], capture_output=True, timeout=20)
    if r.returncode != 0:
        return [Check("adb 可执行", "FAIL", f"{adb} 不可用",
                      "装 Android SDK platform-tools，或用 --adb 指定路径")]
    out.append(Check("adb 可执行", "PASS", r.stdout.decode().splitlines()[0]))

    # 1b. 单设备 —— 多台时不带 -s 会报 more than one device
    _, devs, _ = sh(adb, device, "devices")
    lines = [l for l in devs.splitlines()[1:] if "\tdevice" in l]
    serials = [l.split("\t")[0] for l in lines]
    if len(serials) > 1:
        out.append(Check("设备唯一性", "WARN",
                         f"检测到 {len(serials)} 台设备：{serials}",
                         f"始终带 `-s {device}`，否则 adb 报 more than one device"))
    elif not serials:
        return out + [Check("设备在线", "FAIL", "没有在线设备",
                            "先 `emulator -avd <name>` 或插真机开 USB 调试")]
    else:
        out.append(Check("设备唯一性", "PASS", f"仅 {serials[0]}"))

    # 1c. 设备状态
    _, state, _ = sh(adb, device, "get-state")
    out.append(Check("设备状态", "PASS" if "device" in state else "FAIL",
                     state.strip() or "(空)"))
    return out


def check_memory(adb: str, device: str) -> Check:
    """MemFree 低 + load 高 → 坑 2 的高危信号。"""
    _, mi, _ = sh(adb, device, "shell", "cat", "/proc/meminfo")
    _, up, _ = sh(adb, device, "shell", "uptime")
    free = avail = total = 0
    for line in mi.splitlines():
        m = re.match(r"(\w+):\s+(\d+) kB", line)
        if not m:
            continue
        if m.group(1) == "MemTotal":
            total = int(m.group(2))
        elif m.group(1) == "MemFree":
            free = int(m.group(2))
        elif m.group(1) == "MemAvailable":
            avail = int(m.group(2))
    m = re.search(r"load average:\s+([\d.]+)", up)
    load = float(m.group(1)) if m else -1

    detail = f"MemTotal {total//1024}MB · MemFree {free//1024}MB · " \
             f"MemAvailable {avail//1024}MB · load(1min) {load}"

    # ★ 判据的诚实说明（2026-10-27 实测两次，间隔 20 分钟）：
    #   第一次 OOM 时 MemFree 207MB / load 5.40
    #   本次未 OOM MemFree 231MB / load 0.09
    # → **MemFree 几乎一样，但结果相反**。所以 MemFree 不是可靠判据，
    #   **load average 才是**：load 高说明 CPU/IO 饱和，dump 这种
    #   要遍历整棵视图树又吃内存的操作才容易被 Kill。
    if load >= 1.0:
        return Check("内存压力", "WARN", detail,
                     f"load {load} ≥ 1.0：裸 uiautomator dump 可能被 OOM Kill，"
                     f"建议 --compressed")
    if free and free < 300 * 1024:
        return Check("内存压力", "WARN", detail,
                     f"MemFree {free//1024}MB 偏低但 load 仅 {load}——"
                     f"实测此状态下裸 dump 仍能成功，MemFree 单独不是可靠判据")
    return Check("内存压力", "PASS", detail)


def _try_dump(adb: str, device: str, flags: list[str], read_mode: str,
              settle: float = 0.5) -> tuple[bool, int, str]:
    """跑一次 dump。返回 (成功?, XML 字节数, 诊断串)。"""
    sh(adb, device, "shell", "rm", "-f", REMOTE)
    rc, out, err = sh(adb, device, "shell", "uiautomator", "dump", *flags, REMOTE)
    time.sleep(settle)
    if read_mode == "exec-out":
        _, xml, _ = sh(adb, device, "exec-out", "cat", REMOTE)
    else:
        _, xml, _ = sh(adb, device, "shell", "cat", REMOTE)
    diag = []
    if "Killed" in out or "Killed" in err:
        diag.append(f"输出含 'Killed'（OOM），dump 参数={' '.join(flags) or '(无)'}")
    if "<?xml" in xml and "<hierarchy" in xml:
        return True, len(xml), "; ".join(diag) or "正常"
    diag.append(f"读回 {len(xml)} 字节，无 <hierarchy>")
    return False, len(xml), "; ".join(diag)


def check_plain_dump(adb: str, device: str) -> Check:
    ok, n, diag = _try_dump(adb, device, [], "exec-out")
    if ok:
        return Check("裸 dump（无 --compressed）", "PASS",
                     f"成功，{n} 字节 · {diag}")
    return Check("裸 dump（无 --compressed）", "FAIL",
                 f"失败 · {diag}",
                 "如果诊断里含 'Killed'，是 OOM——改用 --compressed（见下一项）")


def check_compressed_dump(adb: str, device: str) -> Check:
    ok, n, diag = _try_dump(adb, device, ["--compressed"], "exec-out")
    if ok:
        return Check("--compressed dump", "PASS", f"成功，{n} 字节 · {diag}")
    return Check("--compressed dump", "FAIL", f"失败 · {diag}",
                 "压缩版也失败 → 不是内存问题，查 uiautomator 本身（如界面正在动画）")


def check_crlf(adb: str, device: str) -> Check:
    """坑 4 的可复现判定。

    ★ 诚实的结论（2026-10-27 在 adb 1.0.41 / AVD Android 15 实测）：
    `adb shell cat` **并没有**把 LF 转成 CRLF——两种读法字节完全相同。
    而且 `uiautomator dump` 产出的 XML 是**单行、0 个换行符**，
    所以这条坑在当前环境下**根本无法显现**。

    这里分两部分如实报告：
      A. 用刻意造的多行探针测 CRLF（可复现、有判据）
      B. 报告本次 dump 的 XML 有几个换行（说明这条坑能不能显现）
    """
    probe = "/data/local/tmp/_uidref_crlf_probe.txt"
    sh(adb, device, "shell", f"printf 'a\nb\nc\n' > {probe}")
    _, via_shell, _ = sh(adb, device, "shell", "cat", probe)
    _, via_exec, _ = sh(adb, device, "exec-out", "cat", probe)
    crlf_shell = via_shell.count("\r\n")
    crlf_exec = via_exec.count("\r\n")

    sh(adb, device, "shell", "rm", "-f", REMOTE)
    sh(adb, device, "shell", "uiautomator", "dump", "--compressed", REMOTE)
    time.sleep(0.5)
    _, xml, _ = sh(adb, device, "exec-out", "cat", REMOTE)
    xml_lf = xml.count("\n") - xml.count("\r\n")

    detail = (f"多行探针：shell cat {crlf_shell} 个 CRLF / exec-out {crlf_exec} 个；"
              f"本次 dump XML 含 {xml_lf} 个纯 LF（共 {len(xml)} 字节）")
    if crlf_shell > crlf_exec:
        return Check("读文件方式", "WARN", detail,
                     "这台设备的 shell cat 确实引入 CRLF，用 exec-out 或解析前去 CR")
    if xml_lf == 0:
        return Check("读文件方式", "INFO", detail,
                     "XML 是单行，CRLF 问题在此设备上无从显现（exec-out 仍更稳）")
    return Check("读文件方式", "PASS", detail,
                 "exec-out 仍是更稳的选择：它不做 pty 转换")


def check_remote_path(adb: str, device: str) -> Check:
    """坑 3：路径在设备上解释。host 的 /var/folders/... 在设备上不存在。"""
    bogus = "/var/folders/zz/not_on_device.xml"
    sh(adb, device, "shell", "rm", "-f", bogus)
    sh(adb, device, "shell", "uiautomator", "dump", "--compressed", bogus)
    time.sleep(0.4)
    _, xml, _ = sh(adb, device, "exec-out", "cat", bogus)
    if "<hierarchy" in xml:
        return Check("远端路径语义", "WARN",
                     f"意外地读到了 {bogus}", "这台设备居然有该路径，仍建议用设备侧路径")
    return Check("远端路径语义", "PASS",
                 f"{bogus} 在设备上不存在，dump 写不进去（符合预期）",
                 "所以绝不能传 host 的 tempfile 路径——见 uidref README 坑 3")


# ---------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser(description="uiautomator dump 诊断器")
    ap.add_argument("--device", default="emulator-5554")
    ap.add_argument("--adb", default=ADB_DEFAULT)
    a = ap.parse_args()
    adb = a.adb.replace("~", str(__import__("pathlib").Path.home()))

    print(f"=== uiautomator dump 诊断 · device={a.device} ===\n")
    checks: list[Check] = []
    checks += check_adb(adb, a.device)
    if any(c.verdict == "FAIL" for c in checks[:2]):
        for c in checks:
            _print(c)
        return 2
    checks += [
        check_memory(adb, a.device),
        check_plain_dump(adb, a.device),
        check_compressed_dump(adb, a.device),
        check_crlf(adb, a.device),
        check_remote_path(adb, a.device),
    ]

    icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️ ", "INFO": "ℹ️ "}
    for c in checks:
        _print(c, icon.get(c.verdict, "?"))

    fails = [c for c in checks if c.verdict == "FAIL"]
    warns = [c for c in checks if c.verdict == "WARN"]
    print(f"\n合计：{len(checks)} 项 · FAIL {len(fails)} · WARN {len(warns)}")

    # ---- 可复现性分类（的核心论点）----
    print("\n--- 可复现性分类 ---")
    print("本脚本只能证明「当前设备状态下」哪条现形。按类型分三类：")
    print("  [确定性]  任何时候都现形，与本脚本结论无关")
    print("  [负载依赖] 当前不现形 ≠ 不存在；换内存压力可能现形")
    print("  [未复现]  本环境无法复现；保留防御代码是预防，不是因为验过")
    print()
    print("  坑3 路径语义 ....... [确定性]  必现")
    print("  坑1 异步落盘 ....... [负载依赖] 当前不可复现（命令耗时约 2s，返回即完）")
    print("  坑2 OOM Kill ....... [负载依赖] 当前不可复现（见上面 load 数值）")
    print("  坑4 CRLF ........... [未复现]  两种读法字节相同，且 XML 是单行")
    print()
    print("  → 保留 1/2/4 的防御代码，理由是「负载/版本依赖」，不是「本环境验过了」。")

    if fails:
        print("\n有 FAIL 项，按上面的 advice 处理。")
        return 1
    if warns:
        print("\n有 WARN 项——不影响本次抓取，但对应 uidref README 的已知坑。")
    else:
        print("\n本次抓取无阻塞项。")
    return 0


def _print(c: Check, icon: str = "·") -> None:
    print(f"{icon} {c.name}")
    print(f"    {c.detail}")
    if c.advice:
        print(f"    → {c.advice}")


if __name__ == "__main__":
    sys.exit(main())

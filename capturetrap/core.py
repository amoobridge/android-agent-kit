"""capturetrap：`uiautomator dump` 抓取层的四个陷阱。

**它保护的是观测装置本身**——装置的失败会被当成被测对象的失败。
"""

from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET


# --------------------------------------------------------------------- #
# 正确的抓取函数（C1–C4 全部规避）
# --------------------------------------------------------------------- #

def capture(adb: str, dev: str, remote: str,
            retries: int = 8, settle: float = 0.3) -> ET.Element:
    """抓界面结构。四个陷阱全部规避。

    C1  uiautomator 是设备侧命令，必须经 `shell`；且检查 returncode/stderr
    C2  二进制读 + decode(..., "replace")，不抛 UnicodeDecodeError
    C3  `find(b"<hierarchy") >= 0`，不用 startswith（输出以 <?xml 开头）
    C4  dump 前 `rm -f`，避免原地覆写读到上一份内容
    """
    # C4
    _run(adb, dev, "shell", "rm", "-f", remote)
    # C1
    rc, _, err = _run(adb, dev, "shell", "uiautomator",
                      "dump", "--compressed", remote)
    if rc != 0:
        raise RuntimeError(f"uiautomator dump 失败 (rc={rc}): {err.strip()}")
    for _ in range(retries):
        import time
        time.sleep(settle)
        # C2
        raw = _run_bytes(adb, dev, "exec-out", "cat", remote)
        # C3
        if raw[:200].find(b"<hierarchy") >= 0:
            return ET.fromstring(raw.decode("utf-8", "replace"))
    raise RuntimeError(f"抓取超时：{remote} 在 {retries} 次轮询后仍无 hierarchy")


def _run(adb: str, dev: str, *a: str):
    p = subprocess.run([adb, "-s", dev, *a], capture_output=True, timeout=30)
    return p.returncode, p.stdout.decode("utf-8", "replace"), \
        p.stderr.decode("utf-8", "replace")


def _run_bytes(adb: str, dev: str, *a: str) -> bytes:
    return subprocess.run([adb, "-s", dev, *a],
                          capture_output=True, timeout=20).stdout


# --------------------------------------------------------------------- #
# 陷阱判定（供测试与审计用）
# --------------------------------------------------------------------- #

def is_valid_capture(raw: bytes) -> bool:
    """C3：有效性判据。★ 用 find，不用 startswith。"""
    return raw[:200].find(b"<hierarchy") >= 0


def startswith_would_fail(xml_head: str) -> bool:
    """C3 的反证：startswith 判据在真实输出上恒为 False。"""
    return not xml_head.lstrip().startswith("<hierarchy")


def looks_like_unknown_command(stderr: str) -> bool:
    """C1：adb 自己报错（而不是设备报错）。"""
    return "unknown command" in stderr


def is_device_side_command(cmd: str) -> bool:
    """C1：这个命令必须经 `adb shell` 吗？"""
    return cmd in {"uiautomator", "am", "pm", "dumpsys", "input",
                   "screencap", "cmd", "settings", "wm", "svc"}

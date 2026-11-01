"""dump 抓取的回退逻辑回归测试。

这三条测试**不碰设备**——用一个假 adb 模拟三种情形。
它们保护的是 那次真机修复：不加这层测试，
将来有人"简化"掉 `--compressed` 回退，测试全绿但设备上会挂。

三种情形：
  A 压缩版直接成功          → 第一次就返回，不试普通版
  B 压缩版失败、普通版成功   → 必须回退（OOM 场景）
  C 两者都失败              → 错误信息要提示可能是内存不足
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "uidref"))

from http_api import capture_via_adb  # noqa: E402

GOOD = '<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0"></hierarchy>'


def _fake_adb(behavior):
    """造一个假 adb：把调了哪些参数记下来，并按 behavior 决定输出。"""
    calls: list[list[str]] = []

    class R:
        def __init__(self, out: str):
            self.stdout = out.encode()
            self.returncode = 0

    def fake_run(cmd, capture_output=True, timeout=None, text=False):
        calls.append(cmd)
        # cmd = [adb, "-s", dev, <mode>, *args]
        args = cmd[3:]
        mode, rest = args[0], args[1:]
        if mode == "shell" and rest and rest[0] == "uiautomator":
            # 记下这次 dump 用了什么参数（有没有 --compressed）
            fake_run.last_dump_flags = [a for a in rest
                                        if a.startswith("-") or a == "--compressed"]
            fake_run.last_dump_flags = [
                a for a in rest if a.startswith("-")
            ]
            return R("")
        if mode == "exec-out" and rest and rest[0] == "cat":
            return R(behavior(fake_run.last_dump_flags))
        return R("")

    return fake_run, calls


class TestCaptureViaAdb:
    def test_compressed_succeeds_first(self):
        """A：压缩版成功 → 只调一次 dump，且带了 --compressed。"""
        fake, calls = _fake_adb(lambda flags: GOOD if "--compressed" in flags else "")
        with patch.object(subprocess, "run", fake):
            out = capture_via_adb("emulator-5554", "/fake/adb", tries=2)
        assert "<hierarchy" in out
        dumps = [c for c in calls
                 if len(c) > 4 and c[4] == "uiautomator"]
        assert len(dumps) == 1, f"应该只 dump 一次，实际 {len(dumps)}"
        assert "--compressed" in dumps[0], "第一次必须是压缩版"

    def test_falls_back_when_compressed_oom_killed(self):
        """★ B：压缩版被 OOM Kill（无文件），必须回退到普通版。

        这正是 AVD 跑 6 小时后的真实形态：不带压缩的被 Kill，
        带压缩的反而成功。**顺序不能反**——先试压缩。
        """
        def behavior(flags):
            # 这里模拟的是"压缩版失败"，所以压缩返回空、普通版返回内容
            return "" if "--compressed" in flags else GOOD

        fake, calls = _fake_adb(behavior)
        with patch.object(subprocess, "run", fake):
            out = capture_via_adb("emulator-5554", "/fake/adb", tries=2)
        assert "<hierarchy" in out
        dumps = [c for c in calls if len(c) > 4 and c[4] == "uiautomator"]
        assert len(dumps) == 2, f"应该先压缩后普通，实际 {len(dumps)}"
        assert "--compressed" in dumps[0]
        assert "--compressed" not in dumps[1], "第二次必须是不带压缩的普通版"

    def test_both_fail_error_mentions_memory(self):
        """★ C：两种都失败 → 错误信息必须提示可能是设备内存不足。

        否则使用者看到 "adb dump 失败" 完全不知道该干嘛。
        """
        fake, _ = _fake_adb(lambda flags: "")
        with patch.object(subprocess, "run", fake):
            with pytest.raises(RuntimeError) as ei:
                capture_via_adb("emulator-5554", "/fake/adb", tries=1)
        msg = str(ei.value)
        assert "Killed" in msg, f"错误信息应提示 OOM：{msg}"
        assert "重启" in msg or "内存" in msg, f"错误信息应给可行动作：{msg}"

    def test_remote_path_is_device_path(self):
        """★ dump 路径必须在设备上解释得了。

        早期 bug：用 host 的 tempfile.mktemp() 得到 /var/folders/...，
        设备上不存在 → dump 永远写不进、轮询全超时。
        """
        fake, calls = _fake_adb(lambda flags: GOOD)
        with patch.object(subprocess, "run", fake):
            capture_via_adb("emulator-5554", "/fake/adb", tries=2)
        dump_cmds = [c for c in calls if len(c) > 4 and c[4] == "uiautomator"]
        remote = dump_cmds[0][-1]
        assert remote.startswith("/data/local/tmp/") or remote.startswith("/sdcard/"), (
            f"远端路径必须是设备侧路径，实际 {remote!r}")
        assert not remote.startswith("/var/"), f"疑似 host 临时路径：{remote!r}"

    def test_uses_exec_out_not_shell_for_read(self):
        """★ 读文件必须用 exec-out：shell 会把 LF 转 CRLF，污染 XML。"""
        fake, calls = _fake_adb(lambda flags: GOOD)
        with patch.object(subprocess, "run", fake):
            capture_via_adb("emulator-5554", "/fake/adb", tries=2)
        reads = [c for c in calls if "cat" in c]
        assert reads, "应该有一次读文件"
        assert all("exec-out" in c for c in reads), (
            f"读文件必须走 exec-out，实际 {reads}")

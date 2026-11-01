"""capturetrap 黄金向量。"""

from __future__ import annotations

from core import (is_device_side_command, is_valid_capture,
                  looks_like_unknown_command, startswith_would_fail)

REAL_HEAD = ("<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
             "<hierarchy rotation=\"0\">")

VALID = [
    {"kind": "valid", "id": "real-head-with-decl",
     "raw": REAL_HEAD.encode(), "expect": True},
    {"kind": "valid", "id": "bare-hierarchy",
     "raw": b"<hierarchy rotation=\"0\">", "expect": True},
    {"kind": "valid", "id": "empty", "raw": b"", "expect": False},
    {"kind": "valid", "id": "nul-padding",
     "why": "文件被并发覆写时的 NUL 填充。",
     "raw": b"\x00" * 200 + b"<hierarchy>", "expect": False},
    {"kind": "valid", "id": "adb-error-text",
     "why": "★ C1：adb: unknown command 的输出也进 stdout。",
     "raw": b"adb: unknown command uiautomator\n", "expect": False},
]

STARTSWITH = [
    {"kind": "startswith", "id": "real-head",
     "head": REAL_HEAD, "expect": True},
    {"kind": "startswith", "id": "bare-hierarchy",
     "head": "<hierarchy rotation=\"0\">", "expect": False},
]

UNKNOWN = [
    {"kind": "unknown", "id": "unknown-command",
     "err": "adb: unknown command uiautomator\n", "expect": True},
    {"kind": "unknown", "id": "device-error",
     "err": "ERROR: could not get idle state.\n", "expect": False},
    {"kind": "unknown", "id": "empty", "err": "", "expect": False},
]

DEVICE_SIDE = [
    {"kind": "device", "id": "uiautomator", "cmd": "uiautomator",
     "expect": True},
    {"kind": "device", "id": "am", "cmd": "am", "expect": True},
    {"kind": "device", "id": "dumpsys", "cmd": "dumpsys", "expect": True},
    {"kind": "device", "id": "input", "cmd": "input", "expect": True},
    {"kind": "device", "id": "devices-is-host-side",
     "why": "★ devices 是 adb 自己的命令，不能加 shell。",
     "cmd": "devices", "expect": False},
    {"kind": "device", "id": "exec-out-is-host-side",
     "cmd": "exec-out", "expect": False},
]

ALL = VALID + STARTSWITH + UNKNOWN + DEVICE_SIDE


def iter_cases():
    yield from ALL

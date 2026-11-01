#!/usr/bin/env python3
"""uidref HTTP API —— 零依赖，只用标准库。

设计取舍（写在这里是为了审计时不用猜）：

1. **默认只绑 127.0.0.1**。本服务能代表调用方点击屏幕，暴露到局域网等于
   把设备交给同网段任何人。要绑 0.0.0.0 必须显式 ``--host 0.0.0.0``，
   且你应当自己在前面加认证/加密。
2. **无认证、无 TLS**。它假设运行在本机、只服务本机客户端。
   跨机使用前必须自行补上。
3. **snapshot 服务端保留**。ref 是快照域内的名字，解析必须回到同一份快照。
   服务端按 snapshot_id 缓存，LRU 上限 32 份。
4. **`/tap` 会真的点屏幕**。它用 `adb shell input tap`，需要 adb 可达。
   只读用法请只调 `/snapshot` 与 `/resolve`。

用法::

    python http_api.py --port 8770                     # 客户端 POST xml
    python http_api.py --port 8770 --device emulator-5554   # 服务端自己抓

接口::

    GET  /healthz
    POST /snapshot     {"xml": "..."} | {"device": "emulator-5554"}
    POST /resolve      {"snapshot_id": "s...", "ref": "e7"}
    POST /tap          {"snapshot_id": "s...", "ref": "e7"}
    GET  /snapshots
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from uidref import Snapshot, StaleRefError, parse_xml  # noqa: E402

__version__ = "0.1.0"

ADB_DEFAULT = str(Path.home() / "Library/Android/sdk/platform-tools/adb")
MAX_SNAPSHOTS = 32


class SnapshotStore:
    """snapshot_id → Snapshot，LRU。"""

    def __init__(self, cap: int = MAX_SNAPSHOTS):
        self._cap = cap
        self._lock = threading.Lock()
        self._d: OrderedDict[str, Snapshot] = OrderedDict()

    def put(self, s: Snapshot) -> str:
        with self._lock:
            self._d[s.snapshot_id] = s
            self._d.move_to_end(s.snapshot_id)
            while len(self._d) > self._cap:
                self._d.popitem(last=False)
        return s.snapshot_id

    def get(self, sid: str) -> Snapshot | None:
        with self._lock:
            s = self._d.get(sid)
            if s is not None:
                self._d.move_to_end(sid)
            return s

    def ids(self) -> list[str]:
        with self._lock:
            return list(self._d)


STORE = SnapshotStore()


def capture_via_adb(device: str, adb: str, tries: int = 6) -> str:
    """用 adb 抓一次 uiautomator dump。

    四个坑，全部是 AVD Android 15 上真机撞出来的（详见 README §已知边界）：

    1. **异步落盘**。``uiautomator dump`` 命令返回时文件往往还没写完，
       紧接着 ``cat`` 会读到空串。所以轮询等文件出现。
    2. **必须加 ``--compressed``**。AVD 长时间运行后（本机实例跑了 6 小时，
       ``MemFree`` 只剩 200MB、load average 5.4），不带 ``--compressed`` 的
       dump 会被 **OOM Kill**：输出 ``Killed``、**不产生任何文件**、
       也不返回非零退出码。压缩版内存减半、文件也减半（22KB → 11KB）。
       这里先试压缩，失败再退回普通版。
    3. **路径在设备上解释**。远端路径必须是设备侧路径（``/data/local/tmp/...``
       或 ``/sdcard/...``），不能传 host 的 ``tempfile.mktemp()`` 结果——
       那会得到 ``/var/folders/...``，设备上不存在，dump 永远写不进去。
    4. **用 ``exec-out`` 而不是 ``shell`` 读文件**。``shell`` 会把 LF 转成
       CRLF。
       ★ 诚实更正（2026-10-27）：原写「污染 XML（uidref 早期踩过）」是过度断言——
       adb 1.0.41 + Android 15 实测 `shell cat` 与 `exec-out cat` 字节相同，且
       dump 的 XML 是单行、0 个换行符，这条坑无从显现。保留 exec-out 是防御性选择。
       详见 docs/AVD-REPRO.md 坑 4。
    """
    def run(*args: str) -> str:
        r = subprocess.run([adb, "-s", device, *args], capture_output=True, timeout=60)
        return r.stdout.decode("utf-8", "replace")

    remote = "/data/local/tmp/_uidref.xml"
    last = ""
    for extra in (["--compressed"], []):
        run("shell", "rm", "-f", remote)
        run("shell", "uiautomator", "dump", *extra, remote)
        for _ in range(tries):
            last = run("exec-out", "cat", remote)
            if "<hierarchy" in last:
                return last
            time.sleep(0.4)
    raise RuntimeError(
        f"adb dump 失败（压缩与普通两种模式各轮询 {tries} 次后仍无 hierarchy）："
        f"{last[:200]!r}。若 adb shell uiautomator dump 输出含 'Killed'，"
        f"是设备内存不足，重启 AVD 即可。")


def tap_via_adb(device: str, adb: str, x: int, y: int) -> None:
    subprocess.run(
        [adb, "-s", device, "shell", "input", "tap", str(x), str(y)],
        capture_output=True, text=True, timeout=30, check=True,
    )


class Handler(BaseHTTPRequestHandler):
    server_version = f"uidref-http/{__version__}"
    adb_path = ADB_DEFAULT
    device = None  # None = 不自带 adb，客户端必须 POST xml

    # 静音默认访问日志（巡航时太吵）；要审计时改回 log_message
    def log_message(self, fmt, *args):  # noqa: A003
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # -------------------------------------------------- 工具
    def _send(self, code: int, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"请求体不是合法 JSON：{e}") from None

    # -------------------------------------------------- 路由
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0].rstrip("/")
        if path in ("", "/healthz"):
            self._send(200, {
                "ok": True,
                "service": "uidref-http",
                "version": __version__,
                "snapshots": len(STORE.ids()),
            })
        elif path == "/snapshots":
            self._send(200, {"snapshot_ids": STORE.ids()})
        else:
            self._send(404, {"error": f"未知路径 {path}"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0].rstrip("/")
        try:
            body = self._body()
        except ValueError as e:
            self._send(400, {"error": str(e)})
            return

        try:
            if path == "/snapshot":
                self._handle_snapshot(body)
            elif path == "/resolve":
                self._handle_resolve(body)
            elif path == "/tap":
                self._handle_tap(body)
            else:
                self._send(404, {"error": f"未知路径 {path}"})
        except StaleRefError as e:
            self._send(409, {"error": "stale_ref", "ref": e.ref,
                             "snapshot_id": e.snapshot_id,
                             "hint": "请重新 POST /snapshot"})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    # -------------------------------------------------- 处理
    def _handle_snapshot(self, body: dict) -> None:
        if "xml" in body:
            xml = body["xml"]
            if not isinstance(xml, str):
                raise ValueError("xml 必须是字符串")
        elif "device" in body or self.device:
            device = body.get("device") or self.device
            xml = capture_via_adb(device, self.adb_path)
        else:
            raise ValueError("需要 xml 或 device 之一；或启动时加 --device")

        s = parse_xml(xml)
        STORE.put(s)
        self._send(200, {
            "snapshot_id": s.snapshot_id,
            "package": s.package,
            "rotation": s.rotation,
            "width": s.width,
            "height": s.height,
            "digest": s.digest(),
            "elements": [
                {
                    "ref": e.ref, "role": e.role, "label": e.label,
                    "bounds": str(e.bounds),
                    "clickable": e.clickable, "scrollable": e.scrollable,
                    "editable": e.editable, "disabled": e.disabled,
                }
                for e in s
            ],
            "metrics": s.metrics(),
        })

    def _load(self, body: dict) -> Snapshot:
        sid = body.get("snapshot_id")
        if not sid:
            raise ValueError("缺 snapshot_id")
        s = STORE.get(sid)
        if s is None:
            raise StaleRefError(body.get("ref", "?"), sid)
        return s

    def _handle_resolve(self, body: dict) -> None:
        s = self._load(body)
        e = s.resolve(body.get("ref", ""))
        self._send(200, {
            "ref": e.ref,
            "role": e.role,
            "label": e.label,
            "x": e.bounds.cx,
            "y": e.bounds.cy,
            "bounds": str(e.bounds),
            "width": e.bounds.width,
            "height": e.bounds.height,
        })

    def _handle_tap(self, body: dict) -> None:
        s = self._load(body)
        e = s.resolve(body.get("ref", ""))
        device = body.get("device") or self.device
        if not device:
            raise ValueError("tap 需要 device（请求里给，或启动时 --device）")
        tap_via_adb(device, self.adb_path, e.bounds.cx, e.bounds.cy)
        self._send(200, {
            "ok": True,
            "ref": e.ref,
            "label": e.label,
            "x": e.bounds.cx,
            "y": e.bounds.cy,
            "device": device,
        })


def main() -> int:
    ap = argparse.ArgumentParser(description="uidref HTTP API")
    ap.add_argument("--host", default="127.0.0.1",
                    help="默认 127.0.0.1。绑 0.0.0.0 前请自行加认证与 TLS")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--device", default=None,
                    help="adb 设备号，如 emulator-5554。给了之后 /snapshot 可省略 xml")
    ap.add_argument("--adb", default=ADB_DEFAULT)
    ap.add_argument("--verbose", action="store_true", help="打印每个请求")
    args = ap.parse_args()

    Handler.device = args.device
    Handler.adb_path = args.adb
    if not args.verbose:
        Handler.log_message = lambda fmt, *a: None  # noqa: E731

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"uidref-http {__version__}  listening on http://{args.host}:{args.port}")
    print(f"  device = {args.device or '(客户端自备 xml)'}")
    print(f"  adb    = {args.adb}")
    if args.host != "127.0.0.1":
        print("  ⚠️  非回环绑定：本服务无认证无 TLS，请确认前面有网关保护")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

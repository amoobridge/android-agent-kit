"""三处 dump 实现的**一致性**守卫。

为什么不抽成共享模块：uidref / agentloop / devapi 刻意保持解耦、
可独立使用（见 uidref README「与 screenpoint / pointparse 的关系」）。
抽公共包会让三个库互相依赖，违背这个定位。

所以改用**源码级一致性测试**：三个实现可以各写一份，
但在四个关键决策上必须一致，否则将来必然分叉。

四个决策：
  1. 先试 `--compressed`，失败再退回普通版（顺序不能反）
  2. 远端路径必须是设备侧路径（不能是 host 的 /var/folders/...）
  3. 读文件用 `exec-out` 而非 `shell`
  4. 错误信息要提示可能是内存不足（否则使用者不知道干嘛）

做法：**读源码做静态断言**，不 import、不跑设备。

### 变异敏感性已验证

5 个变异体全部被抓到（这是"测试不是空转"的证据）：

| 变异体 | 被抓到 |
|---|---|
| 去掉 `--compressed` 回退 | ✅ |
| 远端路径换成 host 路径 | ✅ |
| 读文件改回 `shell cat` | ✅ |
| 回退顺序反转（先普通后压缩） | ✅ |
| 错误信息去掉内存提示 | ✅ |

**第一版有 2 个逃逸**（③ 和 ⑤）：因为测试在**原文**里搜 `exec-out` /
`Killed`，而 docstring 里也提到这些词——注释算通过了。已改成先用 `ast`
剥掉文档字符串再断言。这正是我这几轮一直在防的「用例空转」，
结果自己刚写就犯了一次。

**一个诚实的边界**：第 6 个变异体「只改 docstring、代码不动」**抓不到**，
而且**不该抓**——代码没变、行为就没变，行为级断言不该为注释变化报警。
这里说清楚，免得后人误以为它是漏网。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

IMPLS = {
    "uidref": ROOT / "uidref" / "http_api.py",
    "agentloop": ROOT / "agentloop" / "agentloop" / "device.py",
    "devapi": ROOT / "devapi" / "devapi.py",
}

# 只对**本 checkout 里存在**的实现做一致性断言。
#
# 为什么：uidref 定位是「可独立使用的库」（见 README），
# 而 agentloop / devapi 不一定在同一次检出里。
# 原版用 `assert p.exists()` 硬失败——结果只提取 uidref 时
# 8 条测试全红，看起来像 uidref 坏了，实际是兄弟库不在。
# 这正是本次反复强调的：**装置的失败不能被当成被测对象的失败。**
PRESENT = {n: p for n, p in IMPLS.items() if p.exists()}

# 只检查**在本次检出中存在**的文档——DOCS 里有些属于兄弟库
DOCS = [d for d in (
    ROOT / "uidref" / "README.md",
    ROOT / "agentloop" / "README.md",
    ROOT / "uidref" / "docs" / "AVD-REPRO.md",
) if d.exists()]


def _src(name: str) -> str:
    p = IMPLS[name]
    if name not in PRESENT:
        pytest.skip(f"{name} 不在本次检出中（{p}）")
    return p.read_text(encoding="utf-8")


def _code_only(src: str) -> str:
    """去掉 docstring 和注释，只留代码。

    ★ 这一步是必须的：第一版测试直接在原文里搜 "exec-out" / "Killed"，
    结果**两个变异体逃逸**——把 `self.sh("exec-out", ...)` 改回 `shell`、
    把错误信息里的内存提示删掉，测试都还是绿的。
    原因：**docstring 里也提到这些词**，注释算通过了。

    这正是我这几轮一直在防的「用例空转」，结果自己刚写就犯。
    所以先剥掉文档字符串再断言。
    """
    import ast
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    # 删掉所有 docstring（Expr(Constant(str)) 形态的首语句）
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def _capture_body(src: str) -> str:
    """截取 dump 抓取相关那段**的代码**（已去 docstring/注释）。"""
    code = _code_only(src)
    for marker in ("capture_via_adb", "def dump_xml", "_adb_capture"):
        i = code.find(marker)
        if i != -1:
            # 取该函数起 4000 字符（去文档字符串后函数体短了很多）
            return code[i:i + 4000]
    raise AssertionError("三个实现里一个都没找到")


class TestThreeImplementationsAgree:
    @pytest.mark.parametrize("name", list(IMPLS))
    def test_compressed_tried_first(self, name):
        """★ 决策 1：`--compressed` 必须在普通版**之前**。

        顺序反了就等于没防 OOM——普通版先跑，OOM 时直接失败，
        永远走不到压缩版。
        """
        body = _capture_body(_src(name))
        m = re.search(r'for\s+extra\s+in\s*\(([^)]*)\)', body)
        assert m, f"{name}: 没找到 `for extra in (...)` 的回退结构"
        order = m.group(1)
        assert "compressed" in order, f"{name}: 回退列表里没有 --compressed：{order!r}"
        # `--compressed` 必须出现在第一个位置（空列表 `[]` 之前）
        first = order.split(",")[0]
        assert "compressed" in first, (
            f"{name}: `--compressed` 不是第一个，顺序反了：{order!r}")

    @pytest.mark.parametrize("name", list(IMPLS))
    def test_remote_path_is_device_side(self, name):
        """★ 决策 2：远端路径必须是设备侧路径。

        这是唯一确定性可复现的坑——用 host 的 tempfile.mktemp()
        会得到 /var/folders/...，设备上不存在，dump 永远写不进去。
        """
        # 全文搜，不限于函数体：agentloop 的默认远端路径定义在 __init__ 里，
        # 不在 dump_xml 内（这本身是个可读性弱点，但结构合法）。
        # 只认 .xml 结尾的——adb 可执行文件本身是 host 路径，不算。
        paths = re.findall(r'["\'](/[^"\']*\.xml)["\']', _code_only(_src(name)))
        assert paths, f"{name}: 没找到远端 XML 路径字面量"
        bad = [p for p in paths
               if p.startswith("/var/") or p.startswith("/tmp/")
               or p.startswith("/Users/")]
        assert not bad, (
            f"{name}: 远端路径疑似 host 路径 {bad}——"
            f"adb shell 的路径在设备上解释，必须用 /data/local/tmp/ 或 /sdcard/")

    @pytest.mark.parametrize("name", list(IMPLS))
    def test_reads_with_exec_out(self, name):
        """★ 决策 3：读文件用 `exec-out`。

        诚实说明：本环境实测两种读法字节相同、且 dump XML 是单行，
        所以这条**不是因为验过**才要求，而是 exec-out 语义上就是
        原始字节流、不依赖 pty 行为。
        """
        body = _capture_body(_src(name))
        assert "exec-out" in body, (
            f"{name}: 读文件没有用 exec-out")

    @pytest.mark.parametrize("name", list(IMPLS))
    def test_error_message_mentions_memory(self, name):
        """★ 决策 4：失败信息要提示可能是内存不足。

        否则使用者只看到"轮询 N 次都没等到 XML"，完全不知道该干嘛。
        """
        body = _capture_body(_src(name))
        assert "Killed" in body or "内存" in body, (
            f"{name}: 错误信息没有提示可能是 OOM/内存不足")

    def test_all_three_have_the_fallback_structure(self):
        """三处都必须有 `for extra in (["--compressed"], [])` 形态的回退。"""
        if not PRESENT:
            pytest.skip("没有任何实现文件在本次检出中")
        for name in PRESENT:
            body = _capture_body(_src(name))
            assert re.search(r'for\s+extra\s+in\s*\(', body), (
                f"{name}: 缺少压缩→普通的回退结构")


class TestNoOverclaimInDocs:
    """文档不得再把坑 4（CRLF）说成已验证。

    的教训：我在 把一条未经本环境验证的现象写成了
    "踩过的坑"，扩散到 6 处。这条测试防止再犯。
    """

    # 允许出现的形态：诚实更正、防御性表述、明确标注未复现
    OVERCLAIM_PATTERNS = [
        # 「shell 会把 LF 转成 CRLF，污染 XML」且前后没有免责表述
        re.compile(r"(?<!★ )shell[`\s]*会把?\s*LF\s*转成?\s*CRLF[，,。\s]*污染"),
    ]

    @pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
    def test_no_unqualified_crlf_claim(self, doc):
        if not DOCS:
            pytest.skip("没有任何目标文档在本次检出中")
        text = doc.read_text(encoding="utf-8")
        for pat in self.OVERCLAIM_PATTERNS:
            for m in pat.finditer(text):
                ctx = text[max(0, m.start() - 200):m.end() + 200]
                # 诚实更正/防御性/未复现 三种免责表述，有任一即可
                safe = any(k in ctx for k in
                           ("诚实更正", "过度断言", "防御性", "未复现",
                            "无法复现", "无从显现", "不是"))
                assert safe, (
                    f"{doc.name}: 发现无免责表述的 CRLF 断言：\n{ctx}")

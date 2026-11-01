#!/usr/bin/env bash
# 全套件测试。必须**逐个进入子目录**运行。
#
# 为什么：uidref / screendiff 的 import 路径依赖"当前目录即包父目录"。
# 从仓库根目录跑 `pytest uidref/tests` 时，`uidref` 会解析成
# 仓库根目录/uidref 这个**目录**（命名空间包），而不是其中的 uidref/ **包**，
# 于是 `from uidref import Bounds` 报 unknown location。
#
# 这是既有的目录布局决定的，本脚本不改动它，只把正确的调用方式固定下来。

set -euo pipefail
cd "$(dirname "$0")"

# ★ 防泄漏：不写字节码缓存。
#
# .pyc 的 co_filename 会嵌**绝对源码路径**（含用户名），
# 而跑一次测试就重新生成一批 __pycache__。
# 实测：清理后跑 run-tests.sh，__pycache__ 从 0 → 30 个，
# 且 `strings *.pyc` 能 grep 出 `/Users/<用户名>/...`。
#
# 所以「交付前清一次」是不够的——读者只要跑一次测试，泄漏复现。
# 必须让它根本不写。
export PYTHONDONTWRITEBYTECODE=1

PY=${PYTHON:-python3}

# 转成绝对路径。run() 会在子 shell 里 `cd "$dir"` 再调 "$PY"，
# 相对路径在那里会被解析成 <dir>/.venv/bin/python3，报
#   "./run-tests.sh: line 42: .venv/bin/python3: No such file or directory"
# 实测踩过：用绝对路径测试时这条路径从未被走过，写成相对路径才现形。
case "$PY" in
    /*) ;;                          # 已是绝对路径
    */*) PY="$PWD/$PY" ;;           # 含斜杠：相对当前目录补全
    *)  PY="$(command -v "$PY")" ;; # 裸命令名：交给 PATH 解析
esac
# 子进程也拿绝对路径：mutate_scan.py 读 $PYTHON 起子进程，
# 它自己也会 cd 到库目录，相对路径同样解析不到。
export PYTHON="$PY"

# 版本闸门：本套件要求 Python >= 3.10（dataclass(slots=True)）。
# 不检查的话，旧版解释器会在 import 链深处抛
# `TypeError: dataclass() got an unexpected keyword argument 'slots'`，
# 看起来像代码坏了，实际是解释器太旧。
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "❌ 需要 Python >= 3.10，当前 $("$PY" --version 2>&1)"
    echo "   指定一个较新的解释器：PYTHON=/path/to/python3.12 ./run-tests.sh"
    exit 1
fi

total=0

run() {
    local name="$1" dir="$2"
    printf '%-24s ' "$name"
    if out=$(cd "$dir" && "$PY" -m pytest tests -q 2>&1 | tail -1); then
        echo "$out"
        n=$(echo "$out" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+' || echo 0)
        total=$((total + n))
    else
        echo "❌ 失败：$out"
        exit 1
    fi
}

# JS 侧一致性（跨语言声明）——没有这段，跨语言声明就没有自动化守护
run_js() {
    local name="$1" dir="$2"
    printf '%-24s ' "$name"
    if out=$(cd "$dir" && node js/conformance.js vectors/ 2>&1 | tail -1); then
        echo "✅ $out"
    else
        echo "❌ 失败：$out"
        exit 1
    fi
}

echo "=== 安卓 GUI Agent 可复用库 · 全套件测试 ==="

echo "--- 感知与引用 ---"
run "uidref"        uidref
run "scrollkey"     scrollkey
run "fieldstate"    fieldstate
run "imespec"       imespec
run "blindspot"     blindspot

echo "--- 坐标契约 ---"
run "screenpoint"   screenpoint
run "pointparse"    pointparse

echo "--- 动作与变化 ---"
run "textin"        textin
run "swipefind"     swipefind
run "screendiff"    screendiff
run "crosstrack"    crosstrack

echo "--- 证据方法论 ---"
run "claimcheck"    claimcheck
run "claimaudit"    claimaudit
run "capturetrap"   capturetrap

echo "--- 提案（uidref 引用失效）---"
run "提案03 stale-ref" 提案/03-stale-ref

echo "--- JS 侧一致性（跨语言声明）---"
run_js "uidref/js"        uidref
run_js "screendiff/js"    screendiff

echo "--- 库级变异扫描（测试能否失败）---"
printf '%-24s ' "mutate_scan"
if out=$("$PY" tools/mutate_scan.py 2>&1 | tail -1); then
    echo "✅ $out"
else
    echo "❌ 失败：$out"
    exit 1
fi

echo "-----------------------------------"
echo "合计 $total 条通过"
echo

echo "=== 文档数字一致性（写死的测试数 vs 实测）==="
if "$PY" tools/sync_test_counts.py; then
    echo "✅ 文档数字与实测一致"
else
    echo "❌ 文档里有写死的测试数与实际不符——数字抄进文档那一刻就开始腐化"
    exit 1
fi

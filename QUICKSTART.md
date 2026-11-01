# 5 分钟跑起来

这份指南只做一件事：让你在**一台刚 clone 下来的干净环境**里，把全套 541 条测试跑绿。
不需要安卓设备、不需要网络、不需要 root。

> 每条命令都在 macOS 上实测通过。如果你在 Linux / Windows 上遇到差异，那是本指南的缺口，请提 issue。

---

## 前置条件：一个 Python ≥ 3.10

**这是唯一的硬门槛，也是大多数人会卡住的地方。**

macOS 自带的 `python3` 是 **3.9**，本套件用到了 3.10 才有的 `dataclass(slots=True)`。
用系统 python3 直接跑会看到：

```
❌ 需要 Python >= 3.10，当前 Python 3.9.6
```

这个报错是**版本闸门**故意拦下来的。没有它的话，你会在 import 链深处看到
`TypeError: dataclass() got an unexpected keyword argument 'slots'`——那看起来像代码坏了，
实际只是解释器太旧。

**先看你有没有**：

```bash
python3.12 --version
```

| 结果 | 下一步 |
|---|---|
| `Python 3.12.x` 或更高 | ✅ 继续 |
| `command not found` | 装一个：`brew install python@3.12`，或用 [python.org](https://www.python.org/downloads/) 的安装包 |

> **如果你就在本机跑**：`~/Dev/venv_py312/bin/python3` 已经是 3.12.13 且带 pytest 和 Pillow，
> 可以直接跳到第 3 步，把命令写成
> `PYTHON=~/Dev/venv_py312/bin/python3 ./run-tests.sh`。
> （这条只对本机成立，换机器请按上面的通用步骤建自己的环境。）

---

## 三步

### 1. 拿代码

```bash
git clone https://github.com/luckybeet/android-agent-kit.git
cd Android-will-better
```

### 2. 建一个干净环境（约 3 秒）

```bash
python3.12 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
```

`requirements.txt` 只有两项：

| 包 | 用途 | 不装会怎样 |
|---|---|---|
| `pytest` | 跑测试 | 全部测试无法运行 |
| `Pillow` | blindspot 的 2 条截图测试 | 那 2 条 **skip**，其余 539 条照常 |

所以 Pillow 是可选的。`35 passed, 2 skipped` 和 `37 passed` 都是正确结果。

### 3. 跑测试

```bash
PYTHON=.venv/bin/python3 ./run-tests.sh
```

**预期输出**（最后几行）：

```
uidref/js                ✅ 向量文件 7 个，用例 45 条，失败文件 0 个
screendiff/js            ✅ 向量文件 6 个，用例 27 条，失败文件 0 个
--- 库级变异扫描（测试能否失败）---
mutate_scan              ✅ 变异 33 个 · 逃逸 0 · 未验证 0
合计 541 条通过
✅ 全部一致
✅ 文档数字与实测一致
```

**实测耗时**（macOS / Apple Silicon）：

| 阶段 | 耗时 |
|---|---|
| `python3.12 -m venv .venv` | ~1 秒 |
| `pip install -r requirements.txt` | ~2 秒 |
| `./run-tests.sh` | **~55 秒**（其中变异扫描占约 45 秒） |
| **合计** | **约 1 分钟** |

> 慢的那段是故意的：变异扫描要把 33 处算法逐个改坏、跑测试、再还原，
> 它是「541 条通过」这句话有没有意义的判据。

---

## 你会看到的三段输出

`run-tests.sh` 做三件事，对应三层证据：

| 段 | 内容 | 它防住什么 |
|---|---|---|
| 逐库 pytest | 15 个库各自的测试 | 行为回归 |
| JS 侧一致性 | uidref 45 向量 + screendiff 27 向量，用 Node 跑第二套实现 | 规范只对 Python 成立 |
| 变异扫描 | 故意改坏 33 处算法，看测试是否抓住 | **测试本身是空转的** |

第三段最值得看一眼。它回答的是「541 条通过」这句话有没有意义——如果改坏了代码测试还是绿，那 541 条等于 0 条。

---

## 常见问题

### `❌ 需要 Python >= 3.10`

见上一节。macOS 自带 3.9，**必须**另装。

### `python3.12: command not found`

```bash
brew install python@3.12
```

或者用 [python.org](https://www.python.org/downloads/) 的 .pkg 安装包（装完重开终端）。

### `pip install` 报网络错误

需要能访问 PyPI。如果在你所在的网络下不通，用镜像：

```bash
.venv/bin/pip install -q -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### `ModuleNotFoundError: No module named 'pytest'`

你用了系统 python3 而不是刚建的 venv。确认跑的是 `PYTHON=.venv/bin/python3 ./run-tests.sh`。

### `./run-tests.sh: line 42: .venv/bin/python3: No such file or directory`

**已修**。`run()` 会在子 shell 里 `cd` 到各库目录，相对路径的 `$PY` 在那里解析不到。
现在脚本会把 `$PY` 转成绝对路径。如果你用的是**旧版本**的 `run-tests.sh`，用绝对路径即可绕过：

```bash
PYTHON="$PWD/.venv/bin/python3" ./run-tests.sh
```

### 从仓库根目录跑 `pytest uidref/tests` 报错

**这是已知的、故意的**。15 个库用「目录同名」导入，必须逐个进入子目录跑——
`run-tests.sh` 已经把正确的调用方式固定好了。详见 `run-tests.sh` 顶部的注释。

---

## 5 分钟之后去哪

按你的兴趣挑一个：

| 想了解 | 读这个 |
|---|---|
| 这些库在解决什么问题 | `README.md` §「每个库解决什么」 |
| 为什么这些数字可信 | `docs/CLAIMS.md` + `README.md` §「为什么这些数字可信」 |
| 每个库调用了什么权限 | `docs/AUDIT.md` |
| 哪些结论是不可引用的、为什么 | `docs/REFUTED.md` |
| 挑一个库深入 | 任选一个目录，先读它的 `SPEC.md` 再读 `README.md` |

想动手改？看 `CONTRIBUTING.md`（如果仓库有），或直接在 GitHub 上开 issue 说明你想改什么。

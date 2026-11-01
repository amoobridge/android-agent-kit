# uidref · 安卓 UI 元素引用层

> **English**
>
> A reference layer for Android UI elements: let the model name an element (`e14`) instead of guessing pixel coordinates.
>
> Flattening `uiautomator dump` XML loses most clickable targets, because they are anonymous containers whose labels live in their children.
>
> Verify: `./run-tests.sh`
> 让模型**引用元素**，而不是猜坐标。
>
> `click e14` —— 不是 `click (540, 1200)`

## 这是什么

一个**规范 + 黄金测试向量 + 参考实现 + HTTP API**，把 `uiautomator dump`
的 XML 压成模型读得动的紧凑文本，并给每个可交互元素一个稳定的引用名。

```
原始 XML                                     uidref digest
21 KB / 61 节点                          →   692 B / 10 个元素 / ~173 tokens

[s39129caee313] com.android.settings 1080x2337 rot=0 elements=10
  e1  scroll <scroll 1080x2263>  [0,74][1080,2337]
  e2  btn    Navigate up  [0,74][147,221]
  e3  item   Set time automatically  [0,544][1080,699]
  e4  item   Date · October 27, 2026 (disabled)  [0,699][1080,905]
  ...
```

**实测 16 个真实安卓界面：XML 共 276 KB，digest 共 8.6 KB，压缩 32.3x。**

## 为什么需要它

### 1. 大部分节点是噪音

16 个真实界面共 789 个节点，**可交互的只有 132 个（16.7%）**。

> **更正**：原稿写 17.3%，复算（`tools/recompute_compression.py`）为
> `132/789 = 16.7%`。17.3% 无法由任何已提交输入复现，已更正为复算值。
其余 82.7% 是布局容器和装饰视图。

### 2. 降噪本身有陷阱

实测发现：**可交互节点多数是匿名 `LinearLayout`**——`text` /
`content-desc` / `resource-id` 全空，文字在子孙 `TextView` 上。

任何「只展示有名字的元素」的降噪，都会**静默丢掉大部分可点目标**。
uidref 的规则是：可点行继承子孙文本（上限 4 段），
但 scrollable 容器不继承（它的「标签」等于整页内容）。

### 3. 坐标要模型做算术，ref 只要模型认字

业界主流是让模型算 `x * 1.5`。uidref 让模型说 `e14`，
服务端把 ref 解析成中心点——确定性代码，零算术。

## 快速开始

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v          # 72 条
python conformance.py vectors/      # 45 条一致性用例
node js/conformance.js vectors/  # JS 侧同样 45 条

# 外部实现方：任何「XML 进 JSON 出」的命令都能测
python tools/verify_impl.py vectors/ --cmd "node js/impl.js"
```

```python
from uidref import parse_file

s = parse_file("dumps/settings-main.xml")
print(s.digest())              # 给模型看

e = s.resolve("e8")            # 严格解析，过期抛 StaleRefError
print(e.label, e.bounds, e.bounds.cx, e.bounds.cy)

# 模型说点 e8：
#   adb shell input tap 540 1710
```

## HTTP API

零依赖，只用 Python 标准库。

```bash
python http_api.py --port 8770 --device emulator-5554
```

```bash
# 抓一份快照（服务端自己调 adb）
curl -X POST localhost:8770/snapshot -d '{"device":"emulator-5554"}'

# 把 ref 解析成中心点
curl -X POST localhost:8770/resolve -d '{"snapshot_id":"s39129caee313","ref":"e8"}'
# → {"x":540,"y":1710,"bounds":"[0,1607][1080,1813]", ...}

# 真点
curl -X POST localhost:8770/tap -d '{"snapshot_id":"s39129caee313","ref":"e6","device":"emulator-5554"}'
```

接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/healthz` | 存活与版本 |
| POST | `/snapshot` | 传 `xml` 或 `device`，返回 digest + elements + metrics |
| POST | `/resolve` | `snapshot_id` + `ref` → 中心点与 bounds |
| POST | `/tap` | 解析后真点（`adb shell input tap`） |
| GET | `/snapshots` | 当前存活的快照 id |

**stale ref 返回 HTTP 409**，响应体提示重新 snapshot。

### 安全取舍（审计必读）

- **默认只绑 `127.0.0.1`**。本服务能代表调用方点击屏幕，暴露到局域网
  等于把设备交给同网段任何人。绑 `0.0.0.0` 必须显式 `--host 0.0.0.0`。
- **无认证、无 TLS**。假设运行在本机、只服务本机客户端。
- 只读用法请只调 `/snapshot` 与 `/resolve`，别调 `/tap`。

## 真机验证

AVD `avd-api35`（Android 15，1080x2400）：

| 界面 | 节点 | 元素 | XML | digest | 压缩 | tokens |
|---|---|---|---|---|---|---|
| settings-storage | 85 | 11 | 29,361 B | 633 B | 46.4x | 158 |
| calendar | 21 | 2 | 7,452 B | 155 B | 48.1x | 38 |
| contacts | 60 | 9 | 22,079 B | 512 B | 43.1x | 128 |
| settings-sound | 71 | 6 | 24,497 B | 387 B | 63.3x | 96 |
| launcher | 33 | 15 | 12,315 B | 754 B | 16.3x | 188 |
| settings-security | 53 | 9 | 20,027 B | 533 B | 37.6x | 133 |
| 其余 10 个 | — | — | — | — | 18.9x – 36.9x | 51 – 212 |

- **可交互召回率 100%**：用独立重算校验，不复用实现自身的判定逻辑
- **标签覆盖率 92.4%**
- **每个界面 digest ≤ 400 tokens**

一次真实点击的副作用验证：点 `e6`「自动设置时间」后，
下一份快照里 `e7` 标签从 "Location may be used to set time zone"
变成 "Automatic time zone is off"，`e8`「时区」从 disabled 变 enabled。
**界面真的变了——这正是 ref 必须绑定快照的实证。**

复现：

```bash
python tools/capture_dumps.py                 # 抓 16 个真实界面
python -m pytest tests/ -q                     # 含真实 dump 回归与指标断言
python http_api.py --port 8770 --device emulator-5554
```

## 跨语言一致性

uidref 的交付物是**规范 + 黄金向量**，不是某一语言的测试套件。
所以它有**两个独立实现**：Python（`uidref/`）与 JavaScript（`js/`，零依赖）。

JavaScript 实现是**照 SPEC.md 写的，不是 Python 的翻译**。
独立实现撞上的规范歧义已回写规范（见 SPEC §1.1 / §2.4 / §3.1 / §3.3 / §5）。

三层验证：

| 层 | 内容 | 结果 |
|---|---|---|
| 黄金向量 | 45 条，两侧同跑 | Python 45/45 · JS 45/45 |
| 真实 dump | 16 个 AVD 界面，逐字段比对 | **完全一致** |
| 随机差分 | 随机生成 XML，两侧比对 | 5 个 seed × 200 条，**0 分歧** |

```bash
python conformance.py vectors/                 # Python 侧
node js/conformance.js vectors/             # JS 侧
python tools/verify_impl.py vectors/ --cmd "node js/impl.js"   # 语言无关
python tools/fuzz_diff.py --n 500 --seed 7     # 随机差分
```

### 📄 [`docs/PORTABILITY.md`](docs/PORTABILITY.md) —— 规范可移植性验证方法

**本文档是整个项目里最不该被跳过的一份。**

它回答一个问题：**"黄金向量全绿" 能证明规范可移植吗？**

答案是不能。uidref 的向量曾达到 34/34 全绿，但其中 **12 条一条都没测到它声称的规则**——
让它们失效的是向量**生成器**的两个 bug，而期望值是用同一份坏输入生成的，所以比较仍然相等。
发现方式不是更仔细地读代码，而是**用第二种语言独立实现了一遍规范**。

文档给出三层可复用的验证法（独立跨语言实现 / 变异敏感性 / 随机差分）、
一份**规范歧义分类学**（T1–T5 + 覆盖盲区）、以及一份**规范作者自查清单**。
这套方法不依赖 uidref，可用于任何规范。

SPEC §10 给出**一致性级别**（Level 1–3），Level 3 才可声称"完整符合本规范"。

### 独立实现逼出来的五处规范修订

| # | 位置 | 问题 | 修订 |
|---|---|---|---|
| A1 | §5 中心点 | 规范写 `(x1+x2)//2` 借用 Python 语法。JS 的 `|0` / `>>1` 向零截断，`Math.floor` 向负无穷。§5 又允许负坐标 → 差 1 | 改为「必须 floor（向负无穷），不是向零截断」 |
| A2 | §3.1 结构性 id | 列举 8 个名字后写「**等**结构性容器名」——开口，各实现自行扩充会破坏确定性 | 改为**穷举集合**，不得自行扩充 |
| A3 | §1 XML 解析 | 未定义输入边界：实体、CDATA、注释、命名空间、畸形输入 | 新增 §1.1 输入子集；明确畸形输入不约束 |
| A4 | §2.4 编号 | 只说「确定性」，未说编号顺序。按 bounds 排序同样确定但 ref 不同 | 明确「前序深度优先文档序，从 e1 连续递增」 |
| A5 | §3.3 继承 | 未说是否含 content-desc、是否跨代、上限是建议 | 明确 text+content-desc、跨代、上限升为必须 4 段 |

### 顺带修掉的两个向量失效 bug

这是跨语言练习**最值钱的副产品**。修订前 34/34 全绿，但其中 **12 条一条都没测到它声称的规则**：

1. **属性名泄漏**：生成器把 `cls=` / `desc=` / `rid=` / `long_clickable=` 当成了字面 XML 属性，
   而真正的 `class=` / `resource-id=` 仍是默认值。
   → "Button → btn" 实际在跑 `android.view.View`（产出 `item`）；
   "EditText → input" 产出 **0 个元素**（View 不算可交互）。
2. **自闭合节点**：`_node()` 恒返回 `<node .../>`，所谓"子孙"其实是**兄弟**。
   → `label-inheritance` 四条用例的标签**全是空串**。

现在 `tests/test_uidref.py::TestVectorsNotVacuous` 有五条元测试守这类 bug，
其中**变异敏感性**是通用防线：改动输入必须改变输出，否则该用例是空转。
已做反向验证——把旧 bug 形态的向量塞回去，4 条元测试立即报警。

## 目录

```
uidref/           库（model.py 类型 / digest.py 解析）
vectors/          7 个黄金向量文件，34 条用例，全部自包含
tests/            72 条 pytest（含真实 dump 回归 + 指标断言）
dumps/            16 个真实 AVD dump（测试素材）
tools/            capture_dumps.py 采集 / gen_vectors.py 生成向量
conformance.py    一致性运行器，可测任意语言实现
http_api.py       HTTP API，零依赖
SPEC.md           规范正文
docs/AVD-REPRO.md   ★ AVD 复现手册：四个坑的实测数据 + 一键诊断脚本说明
tools/diagnose_dump.py  一键判断「我的设备现在能不能抓 dump」
```

## 设计取舍

- **`get()` 宽松，`resolve()` 严格**。检查用前者，执行用后者。
- **禁用节点照样发 ref**。它必须被看见并标 `disabled`。
- **标签上限 60 字符、继承上限 4 段**。防爆。
- **snapshot_id 是内容哈希**。同内容同 id，与文件名无关。
- **`uiautomator dump` 是异步的**：命令返回时文件常未落盘，
  紧接着 `cat` 会读到空串。参考实现轮询等待。

## `uiautomator dump` 的四个坑（AVD Android 15 真机）

四个全部真机撞出来，参考实现 `http_api.capture_via_adb()` 逐个处理。
**但按可复现性分三类——这个分类比"四条都是坑"更诚实：**

| # | 坑 | 类型 | 本环境可复现？ | 处理 |
|---|---|---|---|---|
| 1 | **异步落盘** | 负载依赖 | ❌ 当前不可复现（命令耗时 1.95s，返回即完） | 轮询等 `<hierarchy` |
| 2 | **不带 `--compressed` 被 OOM Kill** | 负载依赖 | ❌ 当前不可复现（load 0.06–0.19） | 先试 `--compressed`，失败退回普通 |
| 3 | **路径在设备上解释** | **确定性** | ✅ **必现** | 用 `/data/local/tmp/...` |
| 4 | **`shell` 走 pty 可能转换换行** | 未复现 | ❌ 两种读法字节相同、XML 单行 | `exec-out`（防御性） |

> **保留 1/2/4 防御代码的理由不是"在本环境验过了"**，而是它们负载/版本依赖——
> 换设备、换 adb 版本、换内存压力下可能现形。坑 3 是确定性的，任何时候都现形。
> 完整实测数据见 `docs/AVD-REPRO.md`。

### ★ 坑 2 值得单独说

AVD 长时间运行后（本机实例跑了 6 小时，`MemFree` 只剩 200MB、
`/proc/meminfo` 显示 MemAvailable 1.1GB、`uptime` load average **5.40**）：

```
$ adb shell uiautomator dump /sdcard/t.xml
Killed
$ ls /sdcard/t.xml
No such file or directory
```

**最难发现的地方：不产文件、也不报错。** 上层只会看到"轮询 6 次都没等到 XML"，
完全看不出是内存问题。

压缩版内存减半、文件也减半（22KB → 11KB）：

```
$ adb shell uiautomator dump --compressed /sdcard/t4.xml
UI hierchary dumped to: /sdcard/t4.xml
-rw-rw---- 1 u0_a193 media_rw 11226 ... t4.xml
```

所以顺序是**先压缩、后普通**——不是反过来。

**坑 4 的诚实更正（2026-10-27）**：原文档写「`shell` 会把 LF 转 CRLF，污染 XML」——
这是**过度断言**。在 adb 1.0.41 + Android 15 上实测：`shell cat` 与 `exec-out cat`
字节完全相同（都是纯 LF），且 `uiautomator dump` 产出的 XML 是**单行、0 个换行符**，
这条坑**无从显现**。保留 `exec-out` 的理由是它语义上就是原始字节流、不依赖 pty 行为，
**不是**因为实测到了污染。详见 `docs/AVD-REPRO.md` 坑 4。

这四条由 `tests/test_capture_fallback.py` 5 条测试守着，
其中 `test_falls_back_when_compressed_oom_killed` 已验证过
**旧实现在这条路径上会失败**（变异敏感性），不是空转用例。

## 与 screenpoint / pointparse 的关系

三个库解耦，同属 Apache-2.0，可独立使用：

| | 管什么 |
|---|---|
| `pointparse` | 模型指了哪（解析模型输出） |
| `screenpoint` | 代码怎么算（坐标空间换算） |
| `uidref` | 模型该指什么（UI 元素引用） |

`uidref` 的价值在于**让前两个库在常见路径上根本不需要**——
能用 ref 就别用坐标。

## 不做的事

- 不做 MCP。对外就是普通 HTTP。
- 不 root、不注入进程、不申请设备管理员、不改第三方应用。
- 不针对任何具体应用做特例。
- 不跨快照复用 ref。

## License

Apache-2.0

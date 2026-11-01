# 安卓 GUI Agent 可复用库 · Android GUI Agent Libraries

**[English](#english)** · **[中文](#中文)**

> 每个库另有独立英文版 `README.en.md`（16 份）；提案 03 有 `PROPOSAL.en.md`。

> 已脱敏：不含本机路径、设备序列号、虚拟设备名。可直接阅读、复现、引用。
> 协议：**Apache-2.0**（每个库根目录各有 `LICENSE`）

---

<a id="english"></a>

## English

A set of reusable libraries for **agents operating Android devices**, plus the
evidence behind them. Every library stays inside one hard boundary:

> **No root. No process injection. No device-admin. No modification of
> third-party apps. Only public system APIs.**

The organising idea: most failures in Android GUI automation are **silent** —
wrong coordinates, taps that land on the keyboard, text that gets truncated or
executed instead of written. These libraries make those failures explicit and
testable rather than plausible-looking.

Each library ships a specification, a reference implementation, golden vectors,
tests, real-device evidence, and a note on *why its numbers can be trusted*.

### Four layers

```
Perception & reference   uidref · scrollkey · fieldstate · imespec · blindspot
Coordinate contract      screenpoint · pointparse · e2e (end-to-end demo)
Action & change          textin · swipefind · screendiff · crosstrack
Evidence methodology     claimcheck · claimaudit · capturetrap
Proposals                uidref reference invalidation (stale-ref)
```

Dependencies are one-directional: coordinate contract → perception & reference
→ action & change. **The evidence methodology layer depends on nothing** and can
be used on its own.

### What each library solves

| Library | In one line |
|---|---|
| `uidref` | Let the agent name an element (`click e14`) instead of guessing coordinates; only 16.7% of dump nodes are interactive |
| `scrollkey` | Content-derived stable keys across scrolling; on a real device **83% of shared rows changed ref** |
| `fieldstate` | Four predicates for whether a field can be written; **`text == ""` is the wrong emptiness test** (it falls back to the hint) |
| `imespec` | Keyboard occlusion and element reachability; on a real device **38.5% of clickable elements are unreachable** |
| `blindspot` | The non-app window that `uiautomator dump` never sees; tapping a "clickable" element lands on the keyboard and **writes into a text field** |
| `screenpoint` | Inverse mapping from model coordinates to device pixels; **the inverse must be deterministic code, never delegated to the model** |
| `pointparse` | Parsing model point output; 38 cases of real dirty output |
| `textin` | How to get text in; `adb shell input text` works for **only 4 of 19 input classes**, and backticks get executed |
| `swipefind` | Validity and absorption of swipe gestures; **a swipe starting on the keyboard writes text**, and the working distance range is not monotonic |
| `screendiff` | Screen-change semantics; across pages its matching is **100% false** |
| `crosstrack` | Trust levels for cross-page tracking; turns silent false matches into an explicit number |
| `claimcheck` | Verification levels for empirical claims; a single observation may only produce a hypothesis, never a conclusion |
| `claimaudit` | Runs the levels across every asset; once caught **11 of 16 claims overstated** |
| `capturetrap` | Silent failures of the observation apparatus; it has silently failed three times itself |

### How to run

```bash
./run-tests.sh
```

Requires **Python ≥ 3.10** (uses `dataclass(slots=True)`). The script has a
built-in version gate, so an older interpreter gets a clear message instead of
`TypeError: dataclass() got an unexpected keyword argument 'slots'` from deep
inside the import chain.

Use a different interpreter:

```bash
PYTHON=/path/to/python3.12 ./run-tests.sh
```

Current result:

```
541 pytest tests pass (plus 8 cross-library consistency tests skipped when a
    sibling library is absent from the checkout)
+ 72 JS golden vectors (uidref 45 + screendiff 27, two independent implementations)
+ 33 library-level mutation scans, 0 escapes
```

After the run, the script cross-checks "test counts written in the docs vs.
actually measured" and fails on mismatch — a number starts rotting the moment it
is copied into a document, and this gate stops it lying quietly.

**No device, no network required.** Real-device tests skip automatically.

### Three honesty notes worth reading first

1. **`screenpoint`'s `fit` / `crop` mapping modes are not verified pixel-by-pixel
   on a real device** — only `stretch` is (648,000 pixels, exact hit). See the
   coverage table in `screenpoint/README.md`.
2. **"An external agent completes the full loop over public APIs" is a proof of
   concept**, run by this project itself, not independently reproduced by a third
   party. `e2e/` and the real-device data are here, but the reproducer is us.
3. **3 quantitative claims are not citable** (1 at V0, single observation; 2 at
   V4, refuted). The list is in **`docs/CLAIMS.md`** and the counter-example
   teaching material is in **`docs/REFUTED.md`** — both inside this kit. (The
   workspace version has 7; the other 4 belong to `agentloop` / `devapi`, which
   this kit does not include.)

### Why these numbers can be trusted

A three-layer evidence chain. Remove any one layer and the other two collapse:

```
capturetrap   →  the observation apparatus is trustworthy (it silently failed 3 times itself)
claimcheck    →  conclusions are graded with justification (the product of five over-claims)
claimaudit    →  the grades are run across every asset (caught 11/16 overstated)
```

Plus two harder criteria:

- **Per-case vacuity meta-tests**: uidref once had 12 golden vectors that, due to
  a generator bug, tested none of the rules they claimed to test
- **Library-level mutation scanning** (`tools/mutate_scan.py`): break each
  library's core algorithm and verify that library's tests **must fail**.
  33 mutants, 0 escapes

### Documentation index

| You want to know | Look at |
|---|---|
| What API each library calls, what permissions it needs, where the user consents, how to stop it | **`docs/AUDIT.md`** (summary) + each library's `审计表.md` |
| Where a number came from, who can recompute it | each library's `docs/` + `data/` (real-device evidence is committed) |
| Why the tests are not vacuous | `TestNotVacuous` meta-tests in each library's `tests/` |
| Which conclusions must not be cited | **`docs/REFUTED.md`** (3 belong to this kit; the other 4 belong to the excluded `agentloop`/`devapi`, kept as teaching material and labelled) |
| What to watch when porting to a second language | `uidref/docs/PORTABILITY.md` |

### Not included (and why)

See [`MANIFEST.md`](MANIFEST.md).

---

<a id="中文"></a>

## 中文

一批面向「**agent 操作安卓设备**」的可复用库。全部遵守同一条硬边界：

> **不 root、不注入进程、不申请设备管理员、不改任何第三方 App，只用系统公开 API。**

核心主张：安卓 GUI 自动化的失败大多是**静默的**——坐标算错、点击落在键盘上、
文本被截断或被当成命令执行。这些库把这类失败变成显式、可测的，而不是
看起来合理的。

每条产出都附带：规范（SPEC）、参考实现、黄金向量、测试、真机取证数据，
以及**这份数字凭什么可信**的说明。

### 四层结构

```
感知与引用     uidref · scrollkey · fieldstate · imespec · blindspot
坐标契约       screenpoint · pointparse · e2e（端到端演示）
动作与变化     textin · swipefind · screendiff · crosstrack
证据方法论     claimcheck · claimaudit · capturetrap
提案           uidref 引用失效（stale-ref）
```

依赖方向是单向的：坐标契约 → 感知与引用 → 动作与变化。
**证据方法论三层不依赖任何其他库**，可单独使用。

### 每个库解决什么

| 库 | 一句话 |
|---|---|
| `uidref` | 让 agent 引用元素（`click e14`）而不是猜坐标；789 节点里只有 16.7% 可交互 |
| `scrollkey` | 跨滚动的稳定元素键；真机上 **83% 的共有行换了 ref** |
| `fieldstate` | 输入框能否写入的四个判定；**`text == ""` 判空是错的**（会回落 hint） |
| `imespec` | 键盘遮挡与元素可及性；真机 **38.5% 的可点元素点不到** |
| `blindspot` | XML dump 的非 App 窗口盲区；点"可点元素"实际落在键盘上，**向输入框写入数据** |
| `screenpoint` | 截图坐标反算；**反算必须由确定性代码完成，不得委托给模型** |
| `pointparse` | 模型指点输出的解析；38 条真实脏数据用例 |
| `textin` | 文本输入怎么送进去；`adb shell input text` **19 类里只有 4 类可用**，反引号会被执行 |
| `swipefind` | 滚动手势的有效性与吸收；**键盘区起滑会写入文本**，有效距离非单调 |
| `screendiff` | 界面变化语义；跨页时 screendiff 的匹配 **100% 是假的** |
| `crosstrack` | 跨页跟踪的信任分级；把静默假匹配变成显式数字 |
| `claimcheck` | 经验性声明的验证等级；单次观测只能产生假设，不能产生结论 |
| `claimaudit` | 把分级跑遍全部资产；曾抓到 **11/16 条虚高** |
| `capturetrap` | 观测装置的静默失效；它自己静默失效过三次 |

### 怎么跑

```bash
./run-tests.sh
```

**要求 Python ≥ 3.10**（用了 `dataclass(slots=True)`）。
脚本内置版本闸门——旧解释器会得到明确提示，而不是在 import 链深处抛
`TypeError: dataclass() got an unexpected keyword argument 'slots'`。

指定别的解释器：

```bash
PYTHON=/path/to/python3.12 ./run-tests.sh
```

### 当前结果

```
541 条 pytest 通过（另有 8 条跨库一致性测试因兄弟库不在本次检出而 skip）
+ 72 条 JS 黄金向量（uidref 45 + screendiff 27，两种语言独立实现）
+ 33 个库级变异扫描，逃逸 0
```

跑完会自动校验「文档里写死的测试数 vs 实测」，不一致直接失败——
数字抄进文档那一刻就开始腐化，这条闸门防止它悄悄说谎。

**不需要设备、不需要网络。** 真机组测试自动 skip。

### 三条必读的诚实标注

1. **`screenpoint` 的 `fit` / `crop` 映射模式未做真机像素级验证**，只验了 `stretch`
   （648,000 像素逐点精确命中）。见 `screenpoint/README.md` 覆盖范围表。
2. **「外部 agent 用公开 API 完成全链路」是概念验证**，由本项目自己跑通，
   非第三方独立复现。`e2e/` 与真机取证数据在，但复现者是我们。
3. **3 条量化声明不可引用**（1 条 V0 单次观测 + 2 条 V4 已推翻），
   清单见 **`docs/CLAIMS.md`**，反例教材见 **`docs/REFUTED.md`**（两份都在本套件内）。
   （工作区版共 7 条，其余 4 条属 `agentloop` / `devapi`，本套件不含那两个库。）

### 为什么这些数字可信

三层证据链，缺任何一层，其余两层都会被拖垮：

```
capturetrap   →  观测装置可信（它自己静默失效过三次）
claimcheck    →  结论分级有据（五次过度声称的产物）
claimaudit    →  把分级跑遍全部资产（抓到 11/16 条虚高）
```

外加两层更硬的判据：

- **逐用例空转元测试**：uidref 曾有 12 条向量因生成器 bug 一条都没测到声称的规则
- **库级变异扫描**（`tools/mutate_scan.py`）：把每个库的核心算法改坏，
  验证该库的测试**必须失败**。33 个变异体，逃逸 0

### 文档索引

| 想知道什么 | 看哪里 |
|---|---|
| 每个库调用了什么 API、要什么权限、用户在哪一步同意、怎么撤销 | **`docs/AUDIT.md`**（总表）+ 各库 `审计表.md` |
| 某个数字怎么来的、谁能复算 | 各库 `docs/` + `data/`（真机取证已提交） |
| 测试为什么不是空转 | 各库 `tests/` 的 `TestNotVacuous` 元测试 |
| 哪些结论不可引用 | **`docs/REFUTED.md`**（3 条属本套件；另 4 条属未含入的 `agentloop`/`devapi`，作为教学材料保留并已标注） |
| 移植到第二种语言要注意什么 | `uidref/docs/PORTABILITY.md` |

### 不在本套件内（及原因）

见 [`MANIFEST.md`](MANIFEST.md)。

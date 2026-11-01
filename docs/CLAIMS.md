# 声明登记表 · 本套件的量化声明

**更新** 2026-10-28 · **判据** `claimcheck` + `claimaudit`

> 本文件登记本套件 14 个资产 + `提案/03-stale-ref` 的量化声明。
> 工作区的 `docs/CLAIMS.md` 覆盖 18 个资产（含 `agentloop` / `devapi` / `e2e` /
> `提案/01,02,04`），本套件不含它们——**它们的声明不进本表**。
> 这是刻意的：一张表只能登记实际交付的东西。

---

## 怎么用这张表

每条量化声明都必须能回答三个问题：

1. **输入是什么？** 合成向量 / 已提交的真机数据 / 现场设备状态？
2. **谁能复算？** 任何人跑测试 / 从 `data/` 重算 / 只有持有设备的人？
3. **数字还是结论？** 设备相关的只承诺结论，不承诺精确值。

---

## 一、四类输入

| 类 | 含义 | 谁能复算 |
|---|---|---|
| **确定性** | 合成向量，断言逐字段相等 | 任何人，`./run-tests.sh` |
| **数据可复算** | 输入已提交到 `dumps/` / `data/`，从数据重算 | 任何人，跑 `tools/` |
| **设备相关** | 依赖现场设备状态 | 只有持有设备的人 |
| **未复现** | 单次观测，未做复现检查 | 没人 |

> **更正**：原表写「任何人，`pytest`」——**不准确**。
> 实测在仓库根跑裸 `pytest` 会报 collection error
> （`ModuleNotFoundError: No module named 'core'`）。
> 原因是各库用目录同名导入（`import core`），pytest 把父目录加进 `sys.path`
> 时解析不到。**必须逐库 `cd` 进去跑**——`run-tests.sh` 已处理好这件事。
>
> 三种调用方式已实测仍全绿：

| 调用方式 | 结果 |
|---|---|
| `bash run-tests.sh`（仓库根） | ✅ 通过 |
| `bash /abs/path/run-tests.sh`（cwd = `/`） | ✅ 通过 |
| `bash ./<pkg>/run-tests.sh`（cwd = 别处，相对路径） | ✅ 通过 |
| 仓库根裸 `pytest` | ❌ collection error |

> `run-tests.sh` 首行 `cd "$(dirname "$0")"` 保证与调用者 cwd 无关。
> **「确定性」类的准确承诺是 `./run-tests.sh`，不是 `pytest`。**

---

## 二、证据台账（claimaudit）

`claimaudit/data/evidence_ledger.json` 登记了本套件 **26 条**量化声明。

| 等级 | 条数 | 含义 |
|---|---|---|
| V0 | 1 | 假设 / 设备相关单次观测 → **不可引用** |
| V1 | 18 | 同一起始状态可重复（含确定性计算） |
| V3 | 5 | 交叉验证 / 多语言独立实现 |
| V4 | 2 | **已推翻** |

**可引用 23 条，不可引用 3 条。**

复算 CLI：

```bash
python claimaudit/tools/audit_claims.py
```

### 全部 26 条

| id | 资产 | 声明 | 等级 | 可引用 |
|---|---|---|---|---|
| `blindspot-behavior` | blindspot | 点 (540,2017) 使搜索框 net → netv（点击落在键盘 v 键） | V1 | ✅ |
| `blindspot-exact` | blindspot | 键盘起点 y=1517 与 IME bounds 精确相等 | V1 | ✅ |
| `blindspot-unreachable` | blindspot | 38.5% 的 XML 可点元素是幻影（5/13 与键盘重叠） | V1 | ✅ |
| `capturetrap-nav` | capturetrap | am start 是恢复原语，不 force-stop 会停在上次页面 | **V4** | ❌ |
| `capturetrap-stale` | capturetrap | 原地覆写：切屏后连续 5 次 dump+cat md5 全部相同 | V0 | ❌ |
| `crosstrack-false-match` | crosstrack | home1 vs sub1 false_match_rate 100%（matched 8 全是垃圾） | V1 | ✅ |
| `fieldstate-b64` | fieldstate | am broadcast --es text_b64 "" 让 am 自己抛异常，广播没发出 | V1 | ✅ |
| `fieldstate-hint` | fieldstate | XML 的 text 在字段为空时回落 hint（'Search settings'） | V1 | ✅ |
| `imespec-unreachable` | imespec | 5/13 不可及（38.5%） | V1 | ✅ |
| `pointparse-vectors` | pointparse | 52 条 pytest + 5 个向量 38 用例全绿 | V3 | ✅ |
| `screendiff-mutation` | screendiff | matched 按标签排序而非下标 → 精确 2/27 失败 | V1 | ✅ |
| `screenpoint-precise` | screenpoint | 648,000 像素逐点精确命中 | V1 | ✅ |
| `scrollkey-reassign` | scrollkey | 滚动序列上 83% 的共有行换了 ref（30/36） | V1 | ✅ |
| `swipefind-200ms` | swipefind | 「200ms 以下完全无效」是复位导致的阈值假象 | **V4** | ❌ |
| `swipefind-kb-write` | swipefind | 键盘区起滑 3/3 复现：net → net by / net be / net gt | V3 | ✅ |
| `swipefind-nonmonotonic` | swipefind | 距离非单调：100/300 ❌ · 600/900 ✅ · 1200/1500 ❌ | V1 | ✅ |
| `swipefind-reset` | swipefind | 「滚过头不可恢复」是复位假象，HOME 键复位后 18/22 | V1 | ✅ |
| `textin-a-b` | textin | A 路 4/19，B 路 19/19 | V3 | ✅ |
| `textin-a-beats-b` | textin | 19 个难例上 B 路（无障碍 SET_TEXT）全部成功，A 路仅 4 个 | V1 | ✅ |
| `textin-c6-three-classes` | textin | 失败分三类：静默 6 / 第三类（rc=0 但 stderr 非空）1 / 有声 8 | V1 | ✅ |
| `textin-semicolon` | textin | 反引号 a\`b\`c → ac（b 被当命令执行） | V1 | ✅ |
| `uidref-compress` | uidref | XML 276 KB → digest 8.6 KB，压缩 32.3x | V1 | ✅ |
| `uidref-coverage` | uidref | 标签覆盖率 92.4% | V1 | ✅ |
| `uidref-diff` | uidref | 16 个真实 dump 逐字段完全一致 + 随机差分 0 分歧 | V3 | ✅ |
| `uidref-recall` | uidref | 可交互召回率 100%（独立重算校验） | V1 | ✅ |
| `uidref-vectors` | uidref | 黄金向量 45 条，Python/JS 两侧全绿 | V3 | ✅ |

---

## 三、★ 复算抓到的 11/16 条虚高（教训留档）

第一版台账（工作区版，16 条）写完，`verify_ledger()` 复算立刻报 11 条不一致。
**"总结自己的证据"这个动作自带乐观偏差。**

| 我写的 | 复算 | 根因 |
|---|---|---|
| uidref 压缩 32.3x = V3 | V0 | `classify()` 假设「观测=采样重复」，而这是**输入已提交的确定性计算** |
| crosstrack false_match 100% = V1 | V0 | 同上 |
| imespec 5/13 不可及 = V1 | V0 | 同上 |

**修正**：`deterministic` 字段。确定性声明靠它升到 V1，**不是靠改观测数**。

**反向修正**：`capturetrap-stale` 我标 V0，复算按 5 次观测算出 V1，
但它有未排除的替代解释（「屏幕真的没变」）→ 降回 V0。

> **一条声明可以被观测多次，同时仍然不可引用。**

**还抓到一条数值错**：uidref README/SPEC 原写「可交互 17.3%」，
复算 132/789 = **16.7%**。三个数字（789 / 773 / 762）互相不一致，
只有 789 能复现。已在三处更正。

---

## 四、不可引用的声明（写文档时必须带标注）

| 资产 | 声明 | 等级 | 为什么 |
|---|---|---|---|
| capturetrap | `am start` 是恢复原语 | **V4** | **已推翻**：换起始状态后不成立 |
| capturetrap | 原地覆写 md5 相同 | V0 | **5 次观测但存在未排除的替代解释** |
| swipefind | 「200ms 以下完全无效」 | **V4** | **已推翻**：复位假象，HOME 键复位后有效 |

> 这 3 条的**反例集与抓住机制**见 [`REFUTED.md`](REFUTED.md)。
> （工作区版共 7 条，其余 4 条属 `agentloop` / `devapi`，不在本套件内。）

---

## 五、设备相关的只承诺结论

本套件的设备相关声明（swipefind / blindspot / imespec / textin / fieldstate / capturetrap）
**只承诺结论，不承诺精确数值**——数值依赖 AVD 与设备状态。

例：`swipefind-kb-write` 只承诺「键盘区起滑会往输入框写文本」这个结论，
不承诺「net → net by」这个具体结果字符串。

> **一条同类教训**：`devapi` 的测试条数写成 38，
> 实测无设备时 36 passed + 2 skipped（AVD 未运行）。
> **一个数字必须说出它在什么条件下成立。**
> （`devapi` 不在本套件内，但同一条规则适用。）

---

## 六、三层证据链

```
capturetrap  →  观测装置可信（它自己静默失效过三次）
claimcheck   →  结论分级有据（过度声称的产物）
claimaudit   →  把分级跑遍全部资产（抓到 11/16 条虚高）
```

**缺任何一层，剩下的两层都会被拖垮。**

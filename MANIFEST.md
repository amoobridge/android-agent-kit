# MANIFEST · 本套件包含什么、脱敏了什么

> 版本日期：2026-10-27

---

## 一、包含的 16 项（541 条测试）

| 层 | 资产 | 测试数 |
|---|---|---|
| 感知与引用 | `uidref/` | 72 passed + 8 skipped |
| 感知与引用 | `scrollkey/` | 21 |
| 感知与引用 | `fieldstate/` | 53 |
| 感知与引用 | `imespec/` | 37 |
| 感知与引用 | `blindspot/` | 37 |
| 坐标契约 | `screenpoint/` | 38 |
| 坐标契约 | `pointparse/` | 52 |
| 坐标契约 | `e2e/` | — （演示，无独立测试） |
| 动作与变化 | `textin/` | 19 |
| 动作与变化 | `textin/refapp/` | — （参考 App，需设备） |
| 动作与变化 | `swipefind/` | 50 |
| 动作与变化 | `screendiff/` | 33 |
| 动作与变化 | `crosstrack/` | 24 |
| 证据方法论 | `claimcheck/` | 38 |
| 证据方法论 | `claimaudit/` | 26 |
| 证据方法论 | `capturetrap/` | 23 |
| 提案 | `提案/03-stale-ref/` | 18 |

---

## 二、脱敏清单

以下本机私有信息已从包内**全部**移除（grep 复验为 0 命中）。
本表只描述类别，不复述原值。

| 类别 | 处理方式 |
|---|---|
| 用户主目录绝对路径（`/Users/<用户名>/...`） | 改为 `Path.home()` 构造或 `python3` |
| 硬编码的虚拟环境解释器路径 | 改为 `os.environ.get("PYTHON", "python3")` |
| 硬编码的 adb 可执行路径 | 改为 `Path.home()` 构造 |
| 工作区绝对路径 | 改为相对定位 `Path(__file__).resolve().parent...` |
| 虚拟设备名（原值含项目标识） | → `avd-api35` |
| 工作区路径注释 | → `仓库根目录` |
| 签名材料（debug keystore / build 产物 / apk / dex） | 已删除并加 `.gitignore` |
| 缓存（`__pycache__` / `.pytest_cache` / `.DS_Store`） | 已清除 |

**保留未改的**：`emulator-5554`（AVD 默认序列号，非私有）、
`Android 15 / Google APIs / arm64-v8a`（复现所需的环境描述）。

**本套件内 grep 上述全部类别，0 命中。**

---

## 三、交付前的固定检查项

每个资产交付前逐条确认：

- [x] License 头是 Apache-2.0
- [x] 无任何第三方应用的具名引用
- [x] 无密钥、无内网路径、无本机绝对路径、无设备序列号
- [x] 测试全绿，且**可在无网络、无设备环境跑**
- [x] README 写明：做什么、不做什么、为什么、怎么验
- [x] 每个规范条文有对应的测试或向量
- [x] 真机验证数据已提交到 `data/`（除设备相关类已标注）
- [x] 无构建产物、无签名材料、无缓存残留
- [x] **文档里引用的每个路径都真实存在**
- [x] **写死的测试数与实测一致**（`tools/sync_test_counts.py`）
- [x] **跑测试不产生 `__pycache__`**（`PYTHONDONTWRITEBYTECODE=1`；
      否则 `.pyc` 的 `co_filename` 嵌绝对路径含用户名，跑一次测试就复现泄漏）

### 本套件顶层文档

| 文件 | 内容 |
|---|---|
| `README.md` | 入口：分层表、怎么跑、三条诚实标注、文档索引 |
| `MANIFEST.md` | 本文件：包含什么、脱敏了什么 |
| `docs/CLAIMS.md` | 26 条量化声明登记（本套件版） |
| `docs/REFUTED.md` | 7 条反例教材 |
| `docs/AUDIT.md` | 各资产的 API / 权限 / 同意点 / 撤销路径 |

---

## 四、仓库形态：先一个，不拆

本套件**以一个仓库交付**，目录结构即分层：

```
android-agent-kit/
├── uidref/ scrollkey/ fieldstate/ imespec/ blindspot/   感知与引用
├── screenpoint/ pointparse/ e2e/                       坐标契约
├── textin/ swipefind/ screendiff/ crosstrack/          动作与变化
├── claimcheck/ claimaudit/ capturetrap/ 提案/           证据方法论
└── docs/ tools/                                        支撑
```

**为什么先不拆**（这是刻意选择，不是没想清楚）：

1. **拆分容易、合并难。** 日后真要拆，`git filter-repo` 按目录切即可；
   先拆成 4 个再想合回来，成本高一个量级。
2. **关注度会碎。** 4 个仓库各 3 star 看起来像失败，1 个仓库 12 star 才是牵引力。
3. **证据链是一个整体。** `claimcheck` / `claimaudit` 是其余 14 个资产数字可信度的凭据，
   拆开后各库的"实测数据"就失去了可信度锚点。
4. **维护成本。** 单人维护 4 个仓库的 README / CI / issue 分拣，是放弃全部的最快路径。

**拆分的触发条件**（满足任一再考虑）：某个层被外部项目实际依赖 /
该层的 issue 量超过其他层总和 / 有第二个人愿意长期维护该层。

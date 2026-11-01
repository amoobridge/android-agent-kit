# screenpoint · GUI Agent 坐标真值层

**[English](README.en.md)** · **[中文](README.md)**


> 让 agent 的每一次点击，落在它以为落的地方。

## 这是什么

一个**规范 + 黄金测试向量 + 参考实现**，解决 GUI Agent 最致命的 silent failure：

模型看到的是**缩放后的截图**，返回的是**该截图坐标系下的点**；agent 必须把它换算回**设备真实像素**。今天业界的主流做法是让 LLM 自己做这个乘法——模型算错，点击落空，且无人察觉。

`screenpoint` 规定：**换算必须由确定性代码完成，不得委托给模型。**

## 为什么需要它

现状（`mobile-next/mobile-mcp` 的做法）：

```
To tap something you see in this screenshot, multiply its x by 1.5 and y by 1.5.
```

四个硬伤：

| # | 问题 | 后果 |
|---|---|---|
| 1 | 让 LLM 做浮点运算 | 模型算术不可靠，误差无界 |
| 2 | ratio 四舍五入到 3 位小数 | 1080px 宽屏上误差可达 0.5px 以上，且随链式操作累积 |
| 3 | 宽高比不一致时无 letterbox/pillarbox 偏移 | 截图贴边留白，按比例硬乘 → 系统性偏移 |
| 4 | 归一化网格（0-1000）无定义反算 | Gemini / UI-TARS 类模型的坐标无处安放 |

## 核心原则

1. **模型只负责"指"，代码负责"算"** —— 反算必须是确定性的
2. **先声明坐标空间，再谈坐标** —— 没有空间声明的坐标是噪音
3. **缩放模式必须显式** —— stretch / fit / crop 的数学不同
4. **取整只在最后一步，且规则唯一** —— 禁止中间取整
5. **越界必须钳制并上报** —— 静默丢弃比报错更糟

## 目录

```
SPEC.md              规范正文（normative）
vectors/             黄金测试向量（JSON，含输入/期望输出/用例来源）
screenpoint/         Python 参考实现
conformance.py       一致性测试运行器（可测任何语言的实现）
tests/               参考实现自测
```

## 快速开始

```bash
pip install -e .
python -m pytest tests/ -v          # 参考实现自测
python conformance.py vectors/      # 跑一致性
```

```python
from screenpoint import Size, Point, CoordinateSpace, map_point

screen = CoordinateSpace("device", Size(1080, 2400))
shot   = CoordinateSpace("model_view", Size(756, 1680))  # 0.7 缩放后喂给模型

# 模型在看到的位置上指了一个点
where_model_pointed = Point(400, 900)

# 确定性反算回设备像素
landing = map_point(where_model_pointed, shot, screen, fit="stretch")
# → Point(571, 1285)
```

## License

Apache-2.0

---

> **English**
>
> Deterministic inverse mapping from model coordinates back to device pixels.
>
> The one deterministic step in the coordinate chain should not be delegated to the model.
>
> Verify: `./run-tests.sh`

## 验证等级

### ⚠️ 真机验证覆盖范围（B4，）

| 缩放模式 | 合成向量 | **真机像素级验证** |
|---|---|---|
| `stretch` | ✅ | ✅ **已验证**（648,000 像素逐点精确命中） |
| `fit` | ✅ | ❌ **未验证** |
| `crop` | ✅ | ❌ **未验证** |

`fit` / `crop` 需要截图留白 / 裁切的场景，AVD 全屏截图构造不出来，
因此**只在合成向量上测过**。其数学公式与 `stretch` 同源（仅 `s` 取法不同），
但**未在真机像素级取证**。

> 按 `claimcheck` 规则：未验证不等于不可用，但**不得声称已验证**。
> 使用 `fit` / `crop` 前请自行验证，或只在其构造留白的场景下使用。

### 本资产的量化声明

量化声明在 **`docs/CLAIMS.md`**（`claimaudit/data/evidence_ledger.json`）登记。

复算：`python claimaudit/tools/audit_claims.py`

**规则**（来自 `claimcheck`）：单次观测只能产生假设，不能产生结论；
低于 V1 不得作为结论引用；已推翻（V4）必须留档并标注「不得作为结论」。

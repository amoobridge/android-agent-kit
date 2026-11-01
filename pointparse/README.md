# pointparse · 模型指点输出的解析与校验

> 宁可报错，不要猜。

## 这是什么

GUI Agent 让模型"点一下那个按钮"，模型会吐回来说不清是什么的东西：

```
{"x": 400, "y": 900}
(400, 900)
x=400, y=900
I'll tap at (400, 900) now.
```json
{"x": 400, "y": 900}
```
{"x": null, "y": null, "reason": "no button visible"}
[100, 200, 300, 400]
1,400, 900
First tap (100, 200), then tap (300, 400).
```

每个 agent 项目都自己写一段正则去啃这些。每段都有 bug，而且**bug 都是静默的**——
解析出一个看起来完全正常的 `(1, 400)`，然后点错地方。

`pointparse` 把这件事做成规范 + 黄金向量 + 参考实现。

## 三条核心原则

1. **拒答不是异常**。模型说"看不到"是正常输出，必须能被优雅处理，
   不能被当成错误吞掉、更不能退化成一个随机坐标。
2. **歧义必须上报**。文本里有两个位置、给的是 bbox、还是 `1,400, 900`
   这种千分位歧义——解析器**不替调用方选**，抛 `Ambiguity`。
3. **空间只给线索，不下结论**。`(0.42, 0.38)` 是归一化还是像素？
   形态上常常无法判定。`infer_space()` 返回枚举线索，调用方必须结合
   自己声明的空间校验。

## 快速开始

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
python conformance.py vectors/
```

```python
from pointparse import parse_point, NoPointFound, Ambiguity

try:
    p = parse_point('{"x": 400, "y": 900}')
except NoPointFound as e:
    # 模型没给指点 —— 正常分支，不是错误
    handle_refusal(e.reason)
except Ambiguity as e:
    # 多个候选，需要人或上层逻辑裁决
    handle_ambiguity(e.candidates)
else:
    tap(p.x, p.y)   # 注意：先结合声明的空间校验，再换算
```

## 与 screenpoint 的分工

```
模型原始输出 ──pointparse──▶ 一个点 + 空间线索
                                    │
                         屏幕声明 + fit 模式
                                    │
                             screenpoint
                                    │
                                    ▼
                            设备可点击像素
```

`pointparse` 管**前端**（模型到底指了哪），`screenpoint` 管**中段**
（代码怎么算）。两者同属 Apache-2.0，可独立使用。

## 支持的格式

| 格式名 | 例子 |
|---|---|
| `dict_xy` | `{"x": 400, "y": 900}` |
| `dict_point` | `{"point": [400, 900]}` |
| `sequence` | `[400, 900]` / `(400, 900)` |
| `paren_csv` | `"(400, 900)"` |
| `bare_csv` | `"400, 900"` / `"<point>400 900</point>"` |
| `kv` | `"x=400, y=900"` |

覆盖的真实脏情况：markdown 包裹的 JSON、带前后缀的 JSON、单引号 JSON、
尾随逗号、中文分号、负坐标、小数坐标、千分位歧义。

## 故意不做的事

- **不给概率**。`infer_space` 返回枚举，不返回"60% 概率是像素"。
  概率会诱使调用方设阈值，而阈值一旦设了就会被绕过。
- **不合并多个候选**。多个位置就是多个位置，报 `Ambiguity`。
- **不区分 list / tuple**。JSON 和多数语言分不出来，把这个区别当成
  不同格式只会让向量不可移植。

## License

Apache-2.0

---

## 验证等级

本资产的量化声明在 **`docs/CLAIMS.md`**（`claimaudit/data/evidence_ledger.json`）登记。

复算：`python claimaudit/tools/audit_claims.py`

**规则**（来自 `claimcheck`）：单次观测只能产生假设，不能产生结论；
低于 V1 不得作为结论引用；已推翻（V4）必须留档并标注「不得作为结论」。

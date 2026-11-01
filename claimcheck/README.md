# claimcheck · 经验性声明的验证等级

**License** Apache-2.0 · **版本** 0.1.0 · **日期** 2026-10-27

---

## 一句话

**单次观测只能产生假设，不能产生结论。**

今天（2026-10-27）我在同一个项目里四次把未复现的观测写成了结论。
四条的共同点：**单次观测 + 漂亮的规律**。
这比一条丑陋的观测更危险——因为它会被直接写进文档、被引用、被当作设计依据。

---

## 四条真实案例

| # | 声明 | 复现检查结果 |
|---|---|---|
| 1 | `adb shell` 把 LF 转 CRLF 污染 XML | 两种读法字节完全相同；XML 单行 0 换行 |
| 2 | `am start`+`BACK` 不能复位滚动位置 | HOME 键可复位；**机制归因错误** |
| 3 | 「200ms 以下手势完全无效」 | **阈值假象**，复位用错导致 |
| 4 | 「`am start` 是恢复原语」 | 换起始状态后**不成立** |

四条全部留在 `data/today_claims.json`，包括原始观测和推翻理由。

---

## 用法

```python
from claimcheck import classify, should_verify_before_writing, refute

# 这条声明够格写进 SPEC 吗？
should_verify_before_writing(observations=1, has_control=True,
                             has_baseline=True)
# → True   ★ 单次观测本身就足够，不需要凑够两个信号

# 它到什么级别？
classify(observations=10, distinct_states=1, independent_channels=1)
# → V1   ★ 复现 10 次但同一起始状态，仍不是 V2

# 被推翻了怎么办？改级 + 留档，不是删除
refute(claim, "换起始状态后不成立")
claim.citable          # → False（即使有 10 次观测）
required_marker(claim) # → "已推翻，不得作为结论"
```

---

## 推翻 ≠ 删除

删掉之后没人知道这里有过一个结论，下一个人会重新发现它。

**`original_observation` + `refuted_by` 本身就是最有价值的教学材料。**
今天第 2 条的机制归因错误，正是在留档之后才被看清的。

---

## 目录

```
claimcheck/
├── SPEC.md      规范：等级 + 危险信号 + 复现协议 + C1–C5
├── README.md    本文件
├── core.py      参考实现
├── vectors.py   黄金向量
├── tests/       38 条 pytest（含元测试 + 今天的四个真实案例）
└── data/
    └── today_claims.json   四条过度声称的完整留档
```

---

## 边界

1. **这是过程规范，不是测量工具。** 它不定"几次算够"，只定"不够时该怎么办"。
2. **不覆盖统计显著性**——本项目观测是确定性界面行为，不是抽样。
3. **不覆盖"观测本身是否可信"**——那是 `capturetrap` 的管界。

---

## 与其他库的关系

`capturetrap` 保证观测**装置**可信；`claimcheck` 保证**结论**不被过度声称。
两者合起来才是完整的证据链。

# 该怎么跟模型说坐标（PROMPT.md）

本文件是 screenpoint 规范的**提示词侧配套**。规范规定代码怎么算，
本文件规定**怎么跟模型说**。

核心只有一句：**别让模型做算术。**

---

## 反模式（业界现状）

```
Screenshot is 756x1680. Screen coordinates are 1080x2400.
To tap something you see in this screenshot, multiply its x by 1.5 and y by 1.5.
```

三个问题：

1. **让 LLM 做浮点乘法**。模型不是计算器，误差不可复现、不可调试。
2. **`1.5` 是预先四舍五入过的**。真实比例是 `1080/756 = 1.428571428...`，
   写 `1.5` 就已经错了（这甚至不是四舍五入，是取了一位有效数字之外的粗近似）。
3. **把确定性环节变成了概率环节**。同一个输入，两次运行可能点在不同像素上。

---

## 正模式（推荐）

把模型当成**指针**，不当计算器。它只负责"我看到了什么、在哪"，
换算全部交给代码。

### 英文版（可直接粘贴）

```
You are looking at a screenshot. When you need to indicate a position,
report the pixel coordinates YOU SEE in the image, as a JSON object
{"x": <int>, "y": <int>} with the origin at the top-left corner.

Rules:
- Do NOT scale, convert, or compute anything. Report the raw pixel
  position as it appears in the image you were given.
- The image you were given is {{WIDTH}}x{{HEIGHT}} pixels.
- If you use a normalized 0-{{GRID_N}} grid instead, say so explicitly
  and state the grid size.
- If you cannot see a suitable target, respond with
  {"x": null, "y": null, "reason": "<why>"}. Never guess.
```

### 中文版

```
你看到的是一张截图。需要指出位置时，请报告你在这张图里看到的像素坐标，
格式为 {"x": <整数>, "y": <整数>}，原点在左上角。

规则：
- 不要做任何缩放、换算、计算。直接报告你看到的原始像素位置。
- 你收到的图片尺寸是 {{WIDTH}}x{{HEIGHT}} 像素。
- 如果你改用 0-{{GRID_N}} 的归一化网格，必须明确说明，并给出网格上界。
- 如果找不到合适目标，返回 {"x": null, "y": null, "reason": "<原因>"}。
  不要猜。
```

---

## 必须一起告诉模型的三件事

| 项 | 为什么 |
|---|---|
| **图片的真实像素尺寸** | 模型看不到图片元数据。不给尺寸，它只能猜坐标系 |
| **原点在左上** | 不声明时，模型可能用左下原点（尤其受过数学训练的模型） |
| **不允许猜** | 猜一个坐标比返回 null 危险得多——猜的坐标看起来完全正常 |

---

## 代码侧配套

拿到模型的输出后，**立刻**用 screenpoint 换算，不要经过任何中间步骤：

```python
from screenpoint import CoordinateSpace, FitMode, Point, to_device_pixel

# 你发给模型的那张图的尺寸 —— 必须和 prompt 里写的一致
shot = CoordinateSpace.pixel("model_view", 756, 1680)
dev  = CoordinateSpace.pixel("device", 1080, 2400)

# 模型返回的原始指点
raw = {"x": 400, "y": 900}

r = to_device_pixel(Point(raw["x"], raw["y"]), shot, dev, fit=FitMode.STRETCH)
if r.clamped:
    # 模型指到了图外 —— 这是模型错误，必须处理，不能直接点
    raise ValueError(f"模型指点越界：{raw}")

adb_tap(r.x, r.y)
```

---

## 自检清单

提交前逐条确认：

- [ ] prompt 里**没有**任何乘除运算要求
- [ ] prompt 里写明了图片的**真实像素尺寸**
- [ ] prompt 里声明了**原点位置**
- [ ] prompt 允许模型返回 **null / 无法确定**
- [ ] 代码侧**第一步**就是 screenpoint 换算，中间没有别的处理
- [ ] 换算结果**检查了 clamped 标记**
- [ ] `fit` 模式是**显式传入**的，不是默认值蒙的

---

## 为什么这条也值得写进规范

因为**提示词是协议的一部分**。代码侧再正确，只要 prompt 让模型做算术，
整条链就废了。规范只管代码不管 prompt，等于修了链条的中段却放着两端漏水。

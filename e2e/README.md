# e2e · 端到端集成演示

> 证明 `pointparse` 与 `screenpoint` 在真机上协同工作。

## 链路

```
① 截图（设备像素 1080x2400）
② 压到模型视图（756x1680，0.7 缩放）
③ 确定目标元素（uiautomator bounds）
④ 假模型用十种脏格式之一吐出指点
⑤ pointparse 解析 → 一个点 + 空间线索
⑥ screenpoint 反算 → 设备可点击像素
⑦ 真点 + 校验落点是否在目标元素内 + 校验界面是否响应
```

"假模型"是确定性的：它在模型视图坐标系里指向 `uiautomator` 给出的某个
可点元素中心，然后随机选一种脏格式输出。这样端到端结果**可精确验证**——
我们知道正确答案是什么。

## 运行

```bash
# 需要 AVD 在跑
~/Library/Android/sdk/platform-tools/adb devices   # 应看到 emulator-5554

python tools/e2e_demo.py
```

依赖：`Pillow`（截图处理）。需要本机 AVD 与 adb。

## 期望输出

```
④ pointparse → (668, 242)  格式=dict_xy  线索=normalized_1000
⑤ screenpoint → 设备像素 (954, 346)  clamped=False
⑥ 已真点 (954, 346)
⑦ 校验：(✓ 命中目标元素内)
   界面响应：✓ 顶层 activity = .accountsettings.mg.ui.main.MainActivity
结论：✓ 端到端跑通
```

## 为什么这一步重要

两个库各自通过测试，只证明它们在**自己假设的世界里**正确。
这一步证明它们在**真实设备、真实 UI、真实坐标系统**里也正确，
而且互相接得上。

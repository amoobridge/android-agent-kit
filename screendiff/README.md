# screendiff

**GUI Agent 界面变化语义层** · Apache-2.0 · v0.1

> 让 agent 知道：**界面变了没有？变了什么？我的动作起作用了吗？**

---

## 一句话问题

主流 agent 用**按位置逐位比对**判断界面变化。这在安卓上系统性失效：

> uidref 的 `ref` 是**位置性**的。列表一滚动，所有 `ref` 全部错位，
> 逐位比对报告「几乎所有元素都变了」——而实际上**没有任何元素出现或消失**，
> 只是整页向上平移了。

真实设备数据（Android 15 AVD，设置页连续上滑）：

| 方法 | 结论 |
|---|---|
| 逐位比对 | 9 / 11 个元素「变化」 |
| **screendiff** | **9 个平移（moved）、0 新增、0 消失、0 状态变化、0 标签变化** |

同一个事实，两种结论。Agent 据此会重复探索、或错误判定动作失败。

**更糟的是相反方向**：列表顶部插入一个新元素时，逐位比对会把**每一个元素**
都标成「变了」，而真正的新元素淹没在噪声里。

---

## 它做什么

两个 uidref Snapshot 进，一个 `ChangeSet` 出：

```
matched   哪些元素是"同一个"（跨快照认出来了）
added     哪些是新的
removed   哪些消失了
changes   每个 matched 元素变的是什么：moved / role / label / state
```

外加三个派生语义：

| API | 回答 |
|---|---|
| `effect(target_ref)` | 我点了 `e7`，起作用了吗？四种结论 + 覆盖层检测 |
| `is_stuck(history, n)` | 连续 n 帧无变化 → **该停了**（agent 止损条件） |
| `is_loading(cur)` | 是不是加载态（应该 级启发式） |

---

## 真机数据

Android 15 AVD，设置应用，三个真实场景：

| 比对 | 场景 | matched | added | removed | moved | state | label |
|---|---|---|---|---|---|---|---|
| `c1→c2` | 主页 → 网络设置页（跨屏导航） | 9 | 2 | 2 | 9 | 0 | 9 |
| `c2→c3` | 打开飞行模式（**单元素状态变化**） | 11 | 0 | 0 | 0 | **1** | **1** |
| `c3→d1` | 列表上滑（**纯平移**） | 11 | 0 | 0 | **9** | 0 | 0 |

**第二行是精度证据**：整个页面只有一个元素变了，screendiff 精确指出是哪一个、
变的是哪一类（`e3` 标签变、`e4` 状态变），其余 9 个元素零误报。

**第三行是价值证据**：9 个元素平移，0 误报。

`effect()` 在同一场景下的输出：

```
effect(e3) = target_changed  changes=['label_changed']     ← 副标题变了
effect(e4) = target_changed  changes=['state_changed']     ← 状态翻转了
effect(e5) = target_unchanged                              ← 点了没反应
```

---

## 两个真机撞出来的算法修正

规范的匹配算法不是纸上设计出来的，是被真实 dump 打脸两次后改定的。

### ① 全屏容器吞掉小元素

设置主页的滚动容器 bounds 是 `[0,74][1080,2337]`，几乎覆盖全屏。
它与页面上**任何**元素的重叠率都 ≥ 0.8。于是纯几何匹配 tier 会让
「头像图片」这种在新页面没有对应物的元素，**匹配到新页面的滚动容器上**，
报告「头像变成了滚动容器」。

**修正**：纯几何 tier 加面积比闸门 `min(area)/max(area) ≥ 0.5`。
小元素 vs 全屏容器的比值趋近 0，直接排除。SPEC §4.1。

### ② 空 `class_name` 被当成「类名相同」

两个匿名元素（可交互行常是匿名 `LinearLayout`）的 `class_name` **都是空字符串**，
于是被判为同类，进而靠几何匹配上，误报率高。

**修正**：三个身份 tier 全部要求对应字段**非空**。空字符串等于
「没有这个信号」，不构成一致性。SPEC §4.1。

两条都有对应的回归测试（`TestSpecRules` / `TestRealDumps::test_no_false_match_across_screens`）。

---

## 安装与使用

```bash
pip install -e .
```

```python
from screendiff import diff, effect_of, is_stuck

cs = diff(prev_snapshot, cur_snapshot)      # uidref 的 Snapshot 直接吃
print(cs.counts)                            # {'matched': 11, 'added': 0, ...}

ef = effect_of(cs, "e7")                    # 我点了 e7
print(ef.conclusion)                        # target_changed / target_unchanged /
                                            # target_gone / unknown_target
print(ef.changes)                           # ('state_changed',)
print(ef.added_overlapping_target)          # 压上来的新面板

if is_stuck(history, 3):
    raise AgentStuck("连续 3 步界面无变化")
```

输入不硬依赖 uidref——任何有 `.elements` 的对象、或 dict 列表都行。

---

## 一致性验证

```bash
python -m pytest tests/ -v                              # 33 条
python conformance.py vectors/                          # Python 侧 27 条
node js/conformance.js vectors/                         # JS 侧同样 27 条
python tools/verify_impl.py vectors/ --cmd "node js/impl.js"   # 语言无关
```

**外部实现方**：只要提供一个「JSON 对进、ChangeSet 出」的命令，
`tools/verify_impl.py` 就能对着黄金向量自测，与你的实现语言无关。
`js/impl.js` 是最小包装范例。

| 层 | 内容 | 结果 |
|---|---|---|
| 黄金向量 | 6 文件 27 用例，两侧同跑 | Python 27/27 · JS 27/27 |
| 跨语言差分 | 120 组随机输入，逐字段比对 | **0 分歧** |
| 真实 dump | 3 对，逐字段比对 | **完全一致** |
| 工具反向验证 | 4 种破坏形态 | **全部检出** |

反向验证的四种破坏形态：

| 破坏 | 检出 |
|---|---|
| 布尔写成字符串 `"true"` | ✅ 18/27 失败 |
| bounds 整体平移 1px | ✅ 19/27 失败 |
| `matched` 按标签排序而非下标（违反 §4.3） | ✅ 精确 2/27 失败 |
| `matched` 顺序倒序（违反 §4.4） | ✅ 6/27 失败 |

---

## 测试里的元测试

`TestNotVacuous` 三级断言，防「用例空转」：

- **A 级**：每条用例至少对一种变异敏感（穷举翻转 7 个标志、平移 bounds、改写 label）
- **B 级（定向）**：声称测某条规则的用例，把该规则改回原状，输出 必须 复原。
  这是真正能抓住「测的是别的东西」那类 bug 的断言
- **C 级**：契约字段齐全——缺字段会让整个验证对真实分歧失明

uidref 曾因向量生成器的属性名泄漏，让 12 条用例一条都没测到它声称的规则
却全部「通过」——因为期望值是用同一份坏输入生成的。这套元测试是为此设的防线。

---

## 项目结构

```
screendiff/
├── SPEC.md            规范正文（含一致性级别 Level 1–3）
├── screendiff/core.py Python 参考实现（零依赖）
├── js/screendiff.js   JavaScript 参考实现（独立编写，非翻译）
├── vectors/           6 个黄金向量文件，27 条用例，全部自包含
├── dumps/             4 个真实 AVD dump（测试素材）
├── conformance.py     Python 侧一致性运行器
├── js/conformance.js  JS 侧一致性运行器
├── tools/
│   ├── gen_vectors.py    向量生成器（含生成期自检）
│   └── verify_impl.py    语言无关一致性验证（外部实现方用）
└── tests/             33 条 pytest
```

---

## 边界（诚实清单）

1. **跨 Activity / 跨包不做前置过滤**。规范比对两个 dump，不判断它们是否
   属于同一界面。调用方应先用 `package` 与 `snapshot_id` 过滤。`c1→c2` 那行
   的 2 added / 2 removed 有一部分就来自跨屏。
2. **WebView / Flutter / 自绘 UI**。这类界面 a11y 树可能整体缺失，
   匹配结果无意义。
3. **超长列表**。全量比对 O(n²)，万级元素不可用。
4. **不假设帧间连续性**。连续滑动的中间帧没采到时，`moved` 距离可能很大。
5. **贪心非全局最优**。选可判定性而非匹配质量，见 SPEC §4.3。
6. **`is_loading` 是 应该 级**。不同应用加载态差异极大，实现可自行调整，
   但调整后不得声称符合这一条。
7. **只在 4 个真实 dump 上验证过**。样本少，指标是方向性的不是统计性的。

---

## 与 uidref 的关系

uidref 解决「一份 XML 怎么变成可交互投影」，screendiff 解决
「两份投影怎么比对」。二者可独立使用，一起用才构成完整链路：

```
uiautomator dump → uidref（XML → Snapshot + refs）
                → agent 决策，输出 ref
                → uidref（ref → bounds → center → tap）
                → uiautomator dump → uidref → screendiff（变了吗？起作用了吗？）
```

## License

Apache-2.0。见 `LICENSE`。

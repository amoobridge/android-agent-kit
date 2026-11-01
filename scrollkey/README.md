# scrollkey

**[English](README.en.md)** · **[中文](README.md)**


**跨滚动稳定元素键** · Apache-2.0 · v0.1

> 让「我刚才点的那一行」在滚动之后还能被找到。

---

> **English**
>
> Content-derived stable keys for UI elements that survive scrolling.
>
> Element refs are positional indices; scrolling reassigns them even when the row itself did not change.
>
> Verify: `./run-tests.sh`

## 问题：ref 表达不了的事

提案03 量化过：**跨页导航 100% 重指派**。双闸门让这种失效报错而不是静默点错，
但代价是每次滚动后引用全作废。

于是有一个真实需求表达不出来：

> 「我刚才点的那一行」——滚动之后怎么再找到它？

`ref` 答不了。它是**序数**，绑定在某一次快照的文档序上。

## 两种寻址方式

| | ref | key |
|---|---|---|
| 语义 | 「**那次**快照里的第 14 行」 | 「**叫 X 的**那一类行」 |
| 绑定 | 快照身份（snapshot_id） | 元素内容 |
| 滚动后 | 失效 | 通常仍有效 |
| 表达 | 身份 | 描述 |

## 键的构造

```
rid:<resource-id>           有 resource-id 且非结构性时优先
lbl:<class-short>:<label>   否则用 类名 + 标签
anon:<class-short>          两者皆空时退化
```

基键在同一快照内重复 k 次时追加 `#<序号>`（0 起，按文档序）。

**结构性 id 不得作为基键**——它是布局容器名，对模型无语义，
且多个元素常共用同一个。

---

## 真机数据（AVD Android 15，系统设置主页，5 帧滚动序列）

相邻两帧各有 **9 行共有**。

### ★ 核心对照：键稳定，ref 每帧都变

跟踪「Sound & vibration」这一行：

```
帧      s0     s1     s2     s3     s4
ref     e11    e9     e6     e4     —
key     同一个字符串，四帧不变
```

跟踪搜索框：

```
帧      s0     s1     s2     s3     s4
ref     e3     e1     e1     e1     e1
key     同一个字符串，五帧不变
```

### ref 换手率：83%

| 迁移 | 共有行 | ref 换手 |
|---|---|---|
| s0→s1 | 9 | **9** |
| s1→s2 | 9 | 7 |
| s2→s3 | 9 | 7 |
| s3→s4 | 9 | 7 |
| **合计** | **36** | **30（83%）** |

**滚动序列上，83% 的共有行换了 ref。** 没有键的话，每一帧都要重新推断
"这是哪一行"——而模型对行身份的误判，会直接变成点错行。

### 冲突：0

16 个真实界面 + 5 帧滚动序列，**132+ 元素，0 个基键冲突**。

但**不得**据此声称"安卓 UI 无冲突"——样本恰好标签唯一。
有重复未命名行的界面（一排同图标、一串同文案开关）一定会冲突，
所以消解逻辑必须有判据（合成向量覆盖）。

---

## 已知边界（诚实清单）

### ① 键不能省掉重新观察 ★最容易误解的一点

**键的价值是维持跨帧的指代连续性，不是省掉重新观察。**

要用键点击，仍然需要当前快照来 `resolve_key` → 拿 ref → 取 bounds。
**该 dump 还是要 dump。**

键省掉的是**重新推断"这是哪一行"**，不是**重新观察界面**。
任何把键宣传成"不用重新 dump"的说法都是错的。
（`test_key_does_not_save_redump` 把这条钉住了。）

### ② 序号只在重复组成员不变时稳定

若滚动导致重复组**在前方新增一行**，组内后续序号整体平移：

```
滚动前   Off#0, Off#1
组前插入  Off#0(新), #1(原#0), #2(原#1)     ← 原 #0 变成 #1
组后新增  Off#0, Off#1, Off#2(新)           ← 安全
```

即：**键不是无条件稳定的**。它与 ref 有同类问题，只是爆炸半径小得多——
只影响同标签的行，而不是整页。

### ③ 标签变了就是键变了

`lbl:` 基键含标签。开关从 Off 变 On，键就变，同一行得到两个键。

**这是设计选择，不是缺陷**：把"标签变了"显式化为"键变了"，
比让键保持不变然后把旧标签当成新标签更安全。

### ④ 匿名元素的键很弱

`anon:` 不含任何内容信息，同 class 匿名元素大量冲突。
此时键退化成"同 class 匿名元素中的第 n 个"，比 ref 只多一层 class 过滤。

---

## 使用

```python
import uidref
from scrollkey import key_map, resolve_key, track

snaps = [uidref.parse_file(p) for p in ["s0.xml", "s1.xml", "s2.xml"]]

# 跨滚动跟踪一行，拿到它每一帧的 ref
refs = track(snaps, "lbl:LinearLayout:Sound & vibration · Volume, haptics, Do Not Disturb")
# → ['e11', 'e9', 'e6']

# 用键点击
el = resolve_key(snaps[2], "lbl:LinearLayout:Sound & vibration · Volume, haptics, Do Not Disturb")
device.tap(el.bounds.cx, el.bounds.cy)
```

**测试**：`pytest tests/ -q` → **21 passed**

## 项目结构

```
scrollkey/
├── SPEC.md              键构造规则 + 四条已知边界 + 实现要求
├── README.md
├── scrollkey.py         base_key / key_map / resolve_key / track + 两个报告
├── dumps/               5 帧真实滚动序列（s0–s4）
└── tests/               21 条 pytest
```

## 与 screendiff 的分工

| | screendiff | scrollkey |
|---|---|---|
| 解决 | 两份快照怎么比对 | 一个元素怎么跨快照指代 |
| 匹配依据 | 几何 + 身份 | **纯内容** |
| 跨页 | 会误配（其边界清单第 1 条） | 不会误配，但跨页就找不到 |

**不得混用**：给键匹配掺几何位置，就继承了 screendiff 已记录的
全屏容器误配问题（`test_no_geometric_matching` 钉住这条）。

## License

Apache-2.0。见 `LICENSE`。

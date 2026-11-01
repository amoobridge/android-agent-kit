# crosstrack

**跨页跟踪的信任分级** · Apache-2.0 · v0.1

> agent 从界面 A 跳到界面 B 之后，哪些指代关系还能信？

---

> **English**
>
> Trust levels for element tracking across screens, with an explicit false-match rate.
>
> Geometric matching across pages produces confident nonsense that looks perfectly reasonable in the numbers.
>
> Verify: `./run-tests.sh`

## ★ 一个真实事故

`screendiff` 比对**设置主页**和**通知子页**：

```
matched 8, added 2, removed 3
```

看起来完全正常。**但这 8 个匹配全是假的**：

| prev（主页） | cur（通知子页） |
|---|---|
| Network & internet · Mobile, Wi-Fi… | App notifications · Control… |
| Apps · Assistant, recent apps… | Conversations · No priority… |
| Storage · 51% used | Notifications on lock screen · Hide… |

**全部标签不同。** 而 `matched 8` 这个数字不会告诉你任何事。

`crosstrack` 就是给这类输出加一层审计：

```
audit_diff(home1, sub1)
  → different_screen
    justified        = 0
    geometric_only   = 8
    false_match_rate = 100%
    shared_keys      = 0
```

**把静默假匹配变成显式数字。**

---

## 三条规则

### ① 同屏判定用 snapshot_id，不用匹配

```python
same_screen(home1, home2)  # True —— 三次进入同一主页，id 完全相同
same_screen(home1, sub1)   # False
```

⚠️ **反向不成立**：id 不同**不代表**换页。滚动也改 id
（scrollkey 量化过：83% 共有行换 ref）。`same_screen() == False`
只能说"内容变了"。

### ② 跨页共有元素用键交集，不用匹配

```python
shared_keys(home1, sub1)   # set()      ← 空，两个界面真没有共有元素
shared_keys(sub1, sub2)    # 10 个键
```

### ③ 跨页解析只认身份，绝不认几何

| tier | 依据 | 跨页可信 |
|---|---|---|
| `rid` | 非结构性 resource-id 相同 | ✅ |
| `label_class` | 类名 + 标签都相同 | ✅ |
| `anon_class` | 仅类名相同 | ❌ |
| `none` | 无身份依据（只可能来自几何匹配） | ❌ |

```python
resolve_across(home1, sub1, "e5")
# → found=False, tier=none, trusted=False
#   主页那行在子页上不存在。**不许**回退到"位置最接近的"。
```

---

## 使用

```python
import uidref
from crosstrack import audit_diff, resolve_across, same_screen, shared_keys

prev = uidref.parse_file("home.xml")
cur  = uidref.parse_file("sub.xml")

a = audit_diff(prev, cur)
print(a.summary())
# different_screen: justified=0 geometric_only=8 false_match_rate=100% shared_keys=0

# 我点的目标行还在吗？
m = resolve_across(prev, cur, "e5")
if not m.trusted:
    ...  # 重新 dump，别猜
```

**测试**：`pytest tests/ -q` → **24 passed**

## 项目结构

```
crosstrack/
├── SPEC.md              三条规则 + 信任级差 + 四条已知边界
├── README.md
├── crosstrack.py        same_screen / shared_keys / identity_tier
│                        / resolve_across / audit_diff
├── dumps/               5 份真实 dump（主页×3 + 通知子页×2）
└── tests/               24 条 pytest
```

## 依赖

叠在 `uidref` / `screendiff` / `scrollkey` 之上。**不修改它们任何一个**
（`test_audit_does_not_modify_screendiff` 钉住这条）。

## 四条已知边界

1. **snapshot_id 不能当换页判据** —— id 不等只说明内容变了
2. **匿名元素跨页一律不可信** —— 两个同 class 匿名元素说明不了任何事
3. **审计是叠加层，不是修复** —— screendiff 的行为完全不变
4. **标签变化会被判为不可信** —— 跨页正确，同屏过度保守；
   同屏的标签变化检测请用 screendiff 的 `effect()`

## License

Apache-2.0。见 `LICENSE`。

# textin · 把文本送进安卓输入框

**License** Apache-2.0 · **日期** 2026-10-27 · **状态** 取证完成，替代路径已真机验证 **19/19**

---

> **English**
>
> Forensics of text input on Android: which inputs survive `adb shell input text`, and an alternative path.
>
> Shell metacharacters are executed on-device, spaces truncate silently, and non-ASCII throws — all with misleading exit codes.
>
> Verify: `./run-tests.sh`

## 一句话

`adb shell input text` 在 **19 类测试输入里只有 4 类能完整落地**。
剩下 15 类里最危险的不是"报错"，是**退出码 0 但只进去一半**。

---

## 为什么值得单独做

GUI agent 迟早要填表单、搜关键字。这件事看起来是一条 adb 命令。

`stepfun-ai/gelab-zero`（MIT，2.3k star）的代码把这件事的难度写得很清楚——
外部项目 gelab-zero 的 copilot_front_end/mobile_action_helper.py（非本仓库路径）：

```python
elif action['action_type'] == "Type":
    text = action['args']['text']
    # adb_command += f" shell input text '{text}'"      ← 注释掉了
    ...
    adb_command += f' shell app_process -Djava.class.path=/data/local/tmp/yadb /data/local/tmp com.ysbing.yadb.Main -keyboard "{text}"'
```

它不用 `input text`，改用 **yadb**：往 `/data/local/tmp` 推 jar、
跑 `app_process` 起一个 Java 进程、走输入法通道。代价是设备上留文件、
起进程，而且**要求键盘已经弹出**（同文件上方专门判断 `keyboard_exists`，
不弹就先点一下输入框）。

而 `copilot_front_end/pu_frontend_executor.py:84-88` 还留着一段
**同样被注释掉的**手动转义残骸：

```python
#     value = value.replace(" ","_").replace("(", "\(").replace(")", "\)")...
```

注意第一个替换是 **把空格换成下划线**——这不是"处理空格"，
这是"放弃空格"。两代实现都被注释掉，信号很强：这个问题不好解。

---

## 真机取证（19 类）

设备：AVD `avd-api35`（Android 15 / Google APIs / arm64-v8a），emulator-5554。
复现：`python tools/probe_input_text.py`（约 4 分钟）

**测试方式很关键**：`subprocess.run([adb, "-s", dev, "shell", "input", "text", text])`
——参数列表，**不经本机 shell**。所以下面所有失败都归因于**设备侧**那一层。

### 干净落地（4 / 19）

```
hello            → hello
a#b              → a#b
a*b?             → a*b?
x × 200          → x × 200
```

长度不是问题，glob 字符也没事——`input` 不是 shell 内建，不经过 glob 展开。

### 空格被静默截断（3 / 19）★最隐蔽

```
hello world      → hello        （退出码 0，无任何报错）
a b%s            → a            （退出码 0）
 pad             → pad          （退出码 0）
```

agent 以为输入了 "hello world"，实际只进去 "hello"。
**这就是 gelab-zero 那段 `replace(" ","_")` 想绕过的东西。**

### 非 ASCII 直接抛异常（2 / 19）★其实最好处理

```
你好世界          → 无变化      adb 退出码 255
                              java.lang.NullPointerException
hi😀ok            → 无变化      adb 退出码 255，同上
```

它**响**。退出码 255 + 明确异常，agent 至少知道失败了。

### 设备侧 shell 解释元字符（8 / 19）★最危险

```
a;b              → a            127  /system/bin/sh: b: inaccessible or not found
a`b`c            → ac             0  /system/bin/sh: b: ...
a$b              → a              0  （$b 变量展开成空）
a|b              → a            127
a&b              → a            127
a(b)c            → 无变化         1  syntax error: unexpected '('
a'b              → 无变化         1  no closing quote
a"b              → 无变化         1  no closing quote
```

**即使本机完全不经 shell，设备侧仍然有一层。**
`adb shell <cmd>` 在设备上等价于 `/system/bin/sh -c <cmd>`。

`a`b`c` → `ac` 这条要特别看：**`b` 是被执行的**。
如果 agent 要输入的文本含反引号，它在设备上跑了一条命令。
这是**注入面**，不只是数据损坏。

### 转义符自身（2 / 19）

```
a%s              → a␣           %s 是 adb 自己的空格转义序列，被解开成空格
a\b              → ab           反斜杠被吃掉
```

---

## 汇总

| 类 | 数量 | 特征 | 危险度 |
|---|---|---|---|
| 干净 | 4 | 完整落地 | — |
| 空格截断 | 3 | **退出码 0，静默** | 高 |
| 非 ASCII | 2 | **退出码 255，有声** | 低 |
| shell 元字符 | 8 | 部分 127 / 部分 1，**可能执行命令** | **最高** |
| 转义符自身 | 2 | 退出码 0，静默 | 中 |

**只有 4/19。** 而"纯 ASCII、无空格、无元字符"恰好是真实任务里
最不常见的那种输入。

---

## ★ 两条路径真机对照（19 用例）

同一段文本、同一个输入框、同一条清场流程，只换落笔的那一步：

| 用例 | 原文 | A `input text` | B `SET_TEXT` |
|---|---|---|---|
| 带空格 | `hello world` | ❌ `hello` | ✅ |
| 中文 | `你好世界` | ❌ 无变化 | ✅ |
| emoji | `hi😀ok` | ❌ 无变化 | ✅ |
| 分号 | `a;b` | ❌ `a` | ✅ |
| 反引号 | `` a`b`c `` | ❌ `ac` | ✅ |
| 美元 | `a$b` | ❌ `a` | ✅ |
| 单引号 | `a'b` | ❌ 无变化 | ✅ |
| 双引号 | `a"b` | ❌ 无变化 | ✅ |
| 竖线 | `a\|b` | ❌ `a` | ✅ |
| 与号 | `a&b` | ❌ `a` | ✅ |
| 圆括号 | `a(b)c` | ❌ 无变化 | ✅ |
| 百分号 | `a%s` | ❌ `a ` | ✅ |
| 空格加百分号 | `a b%s` | ❌ `a` | ✅ |
| 反斜杠 | `a\\b` | ❌ `ab` | ✅ |
| 首尾空格 | ` pad ` | ❌ `pad` | ✅ |
| 纯 ASCII / 井号 / 星号问号 / 长串 200 | — | ✅ | ✅ |

**A 通过 4/19，B 通过 19/19。**

> **失败要分三类看，不是两类**（SPEC C6，）：
> 静默（退出码 0 且 stderr 空）6 条 / **第三类（退出码 0 但 stderr 非空）1 条** /
> 有声（退出码非 0）8 条。
> 第三类就是上面那条反引号——退出码 0 会让"看退出码"的调用方判它成功，
> 而 `b` 确实被执行了。

> ⚠️ **反引号那一行**：A 路回读 `ac`，意味着 `b` 被当成命令**执行**了。
> B 路回读 `` a`b`c ``——文本原样落下，没有任何东西被执行。
> **同一段输入，一条路上是注入面，另一条路上只是字符串。**

复现：`python tools/compare_paths.py`（约 8 分钟）

### 为什么 B 路能全过

文本作为 **Bundle 的一个字段**传给 `performAction`，**不经过任何 shell**。
`input text` 的 15 类失败里有 10 类根源就是设备侧那层 `/system/bin/sh -c`——
`;` `` ` `` `$` `|` `&` `(` `'` `"` 全被它解释；`%s`、反斜杠、空格是
adb 自己的转义层。**绕开 shell，这两层问题一起消失。**

### ★ 但传输层也要证明（否则等于没证）

第一版用 `am broadcast --es text "a\`b\`c"` 直接传，回读 `ac`——
跟 `input text` 的失败一模一样。那不是 SET_TEXT 的错，
是 **`am broadcast --es` 同样经过设备侧 shell**。

必须分开证明两件事：

```
传输（base64）    保证文本原样到达 Bundle      ← base64 字符集无 shell 元字符
API（SET_TEXT）   保证文本原样落进输入框       ← performAction 不经 shell
```

参考实现用 `--es text_b64 <base64>`，两件事一起证。
**只证后者不证前者，等于没证。**

---

## ★ 判定口径：不要假设空字段的 `text` 是空串

实测：设置搜索框（`com.google.android.settings.intelligence`）空的时候：

```
text = "Search settings"        ← 这是提示文字（hint），不是内容
```

所以 `text == ""` 不能用来判断"字段是空的"。

**采用三分判定**，拿输入前的回读当基线，只比较变化：

| 判定 | 条件 |
|---|---|
| **干净** | `after == text` |
| **部分** | `after != before` 且 `text ⊆ after` |
| **无变化** | `after == before` |

---

## 推荐的替代路径

| 路径 | 能处理 | 代价 | root？ |
|---|---|---|---|
| 空格转 `%s` | 仅空格 | 与"想输入 %s"冲突 | 否 |
| 输入法通道（yadb） | unicode + 空格 | 设备留 jar、起 Java 进程、要求键盘已弹 | 否 |
| 剪贴板 + 粘贴 | 完整文本 | 需聚焦长按菜单 | 否 |
| **无障碍 `ACTION_SET_TEXT`** | **完整文本，含 unicode** | 需无障碍权限 | 否 |

**最后一条是推荐的**，理由：

1. 唯一不需要在设备上留文件、起进程的路
2. 文本作为 Bundle 字段传递，**不经过任何 shell** → 注入面整体消失
3. unicode / 空格 / 元字符一律按字符串处理，无转义层
4. `BIND_ACCESSIBILITY_SERVICE` 是公开权限，用户显式开启、随时可关

代价是要无障碍权限——但这正是"agent 操作设备"的正常门槛。
本套件 `uidref` 的**读取**侧已经在用同一把钥匙，写入是同一个权限。

> ⚠️ 这条路径**未在真机验证**。本库只给出论证与推荐，实现留给后续。
> 没验过的不写成已验过。

---

## 文件

```
textin/
├── SPEC.md                       规范：判定口径 + 19 类失败分类 + 真机对照 + 一致性条件
├── README.md                     本文件
├── LICENSE                       Apache-2.0
├── tools/
│   ├── probe_input_text.py       真机取证：`input text` 单独跑（19 用例，约 4 分钟）
│   └── compare_paths.py          真机对照：`input text` vs `SET_TEXT`（约 8 分钟）
├── refapp/                       最小 SET_TEXT 参考 App（Apache-2.0）
└── data/
    ├── probe_results.json        `input text` 单独取证结果
    └── compare_results.json      两条路径对照结果
```

---

## 复现

```bash
# 前提：AVD emulator-5554 在跑
cd textin
python tools/probe_input_text.py                 # 只跑 input text（约 4 分钟）
python tools/probe_input_text.py --verbose       # 附每次的 adb 退出码/stderr
python tools/compare_paths.py                    # input text vs SET_TEXT（约 8 分钟）
```

`tools/compare_paths.py` 需要先装好参考 App 并开启无障碍服务：

```bash
cd refapp && ./build.sh
adb -s emulator-5554 install -r build/textin-refapp.apk
adb -s emulator-5554 shell settings put secure \
    enabled_accessibility_services com.textin.refapp/.SetTextService
adb -s emulator-5554 shell settings put secure accessibility_enabled 1
```

退出码 0 = 全部干净；1 = 存在失败；2 = 装置问题（未聚焦/未清空/无设备）。

---

## 已知边界

1. **取证来自一台 AVD（Android 15 / Google APIs）。** ROM 之间
   `input text` 实现可能有差异，换设备需重跑，**精确计数不外推**。
   （方向性结论——空格截断、非 ASCII 抛异常、元字符被 shell 解释——
   来自 `adb shell` 的通用实现，跨设备应成立。）
2. **未测密码框**：`password="true"` 的字段回读会被屏蔽，判定口径不适用。
3. **未测 `input keyevent` 逐字符输入**：它走另一条路，预期不受 shell 影响，
   但没验。
4. **§对照只覆盖"整段替换"语义**。未测：光标不在末尾时的行为、
   只读字段、以及 `ACTION_SET_TEXT` 与输入法联想状态的交互。

---

## 开发记录：这个探针自己错了五版

| 版 | 错在哪 | 会得出的假结论 |
|---|---|---|
| v1 | 没聚焦输入框，按键全部落空 | "`input text` 100% 坏掉" |
| v2 | 清空不干净，回读恒为上一轮残留 | "所有输入都坏" |
| v3 | 不知道 hint 会被报进 `text`，空字段判为有内容 | 同上 |
| v4 | 判定口径改三分，但基线取自"启动时的 whatever 状态" | 部分对 |
| v5 | 基线恰好是脏的（上一轮残留 200 个 x），"删到等于基线"第一轮就通过 | 又全错 |
| v6 | **基线改为"删到不再变化"**，不依赖任何初始状态 | ✅ |
| v7 | 参照实现用 `--es text` 直传，回读 `ac`——`am broadcast --es` 也过 shell | 假阴性 |
| v8 | 改 `--es text_b64`，传输层与 API 层分开证明 | ✅ 19/19 |

**八版里设备的行为一直是一样的，变的是我的装置。**

v7 尤其值得记：它让我一度以为"SET_TEXT 也过不了 shell"。
实际上 SET_TEXT 从来没碰过 shell——是**我把文本送到它面前的那一步**碰了。
`am broadcast --es` 和 `input text` 一样，都是 `adb shell` 的子命令。

所以 SPEC 把两条立成必须：

- 输入前必须验证 `focused == true`
- 输入前必须验证字段已回到基线

**一条取证结论的可信度，取决于装置本身有没有被判据保护。**

---

## 适用范围

**本库定位**：纯取证、可复现、不点名任何第三方应用、
benefit 全部同类 agent 项目、Apache-2.0。
§6 的推荐路径明确标为未验证，不构成过度声明。

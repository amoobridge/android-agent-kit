# textin/refapp · 最小 SET_TEXT 参考实现

**[English](README.en.md)** · **[中文](README.md)**


**License** Apache-2.0 · **日期** 2026-10-27
**审计说明** [`AUDIT.md`](AUDIT.md) —— 权限清单 / 接触的能力 / 用户同意点 /
撤销路径 / 四个读者会问的点。**不需要读代码即可判断这个 App 接触了什么。**

---

> **English**
>
> A minimal reference implementation of `ACTION_SET_TEXT` over an accessibility
> service — the path that survives shell metacharacters, spaces and non-ASCII,
> where `adb shell input text` does not.
>
> Audit: [`AUDIT.md`](AUDIT.md)


## 一句话

一个**只有两个 Java 文件**的无障碍服务，用来证明
`ACTION_SET_TEXT` 能处理 `adb shell input text` 处理不了的 15 类输入。
**没有 HTTP 服务、没有令牌、不监听端口、不 root。**

---

## 为什么长这样

这是**参考实现**，要展示的是"SET_TEXT 这条路走得通"，
不是"怎么把设备暴露到网络上"。加 HTTP 服务会让最小样例变成一个网络服务，
超出参考实现的范围。

触发走 `adb shell am broadcast`：

```bash
adb shell am broadcast -a com.textin.refapp.SET_TEXT --es text_b64 <base64>
```

---

## ★ 为什么用 `text_b64` 而不是 `text`

第一版用 `--es text "a\`b\`c"` 直传，回读是 `ac`——
跟 `input text` 的失败一模一样。差点写成"SET_TEXT 也过不了 shell"。

**实际上 SET_TEXT 从来没碰过 shell。**
是**把文本送到它面前的那一步**碰了：`am broadcast` 和 `input text` 一样，
都是 `adb shell` 的子命令，`adb shell <cmd>` 在设备上等价于
`/system/bin/sh -c <cmd>`。

所以必须分开证明两件事：

```
传输（base64）    保证文本原样到达 Bundle
API（SET_TEXT）   保证文本原样落进输入框
```

base64 字符集 `[A-Za-z0-9+/=]` 不含任何 shell 元字符，
是"穿过设备 shell 而不被解释"的传输形式。
**只证后者不证前者，等于没证。**

---

## 构建

```bash
cd refapp
./build.sh
```

产物 `build/textin-refapp.apk`（debug 签名，仅供本机验证）。

构建链：`aapt2 compile` → `aapt2 link` → `javac` → `d8` → `zipalign` → `apksigner`。

### 构建脚本里两个坑（都踩过）

**① `--boot-class-path` 在 JDK 9+ / target≥9 时被禁**

```
错误: 目标 17 不允许选项 --boot-class-path
```

`android.jar` 放 `-classpath` 就行：`android.*` 从它来，`java.*` 从 JDK 平台来。

**② keystore 不能放在 `build/` 里、也不能每次重新生成**

v1 把 keystore 放 `build/`、开头又 `rm -rf build`，于是每次构建换一把新 key：

```
INSTALL_FAILED_UPDATE_INCOMPATIBLE: Existing package ... signatures do not match
```

而 `install -r ... | tail -1` 把这行吞了——**我拿着旧 APK 测新代码**，
得出"修复没生效"的假结论。

> 构建系统的失败也是装置的失败。这句话值得记住。

---

## 安装与开启

```bash
adb -s emulator-5554 install -r build/textin-refapp.apk

# 用 settings 直接开，不用手点系统设置界面
adb -s emulator-5554 shell settings put secure \
    enabled_accessibility_services com.textin.refapp/.SetTextService
adb -s emulator-5554 shell settings put secure accessibility_enabled 1

# 验证真的绑上了
adb -s emulator-5554 shell dumpsys accessibility | grep "Bound services"
```

⚠️ **`Bound services:{}` 就是没绑上**，此时发多少广播都不会有结果。
`../tools/compare_paths.py` 启动时会检查这一项，没绑上直接退出（返回码 2），不出具结论。

---

## 使用

```bash
# 1) 打开一个有输入框的界面
adb -s emulator-5554 shell am start -a android.settings.APP_SEARCH_SETTINGS
adb -s emulator-5554 shell input tap 600 230        # 聚焦输入框

# 2) 下发文本
adb -s emulator-5554 shell am broadcast \
    -a com.textin.refapp.SET_TEXT --es text_b64 "$(printf '你好世界' | base64)"

# 3) 读应用自己的报告（应用是 debuggable 的）
adb -s emulator-5554 shell run-as com.textin.refapp cat files/last_result.json

# 4) 独立回读（不信应用自述）
adb -s emulator-5554 shell uiautomator dump --compressed /data/local/tmp/r.xml
adb -s emulator-5554 exec-out cat /data/local/tmp/r.xml
```

---

## 代码里三个值得看的点

### 1. 跨窗口找焦点输入节点

```java
AccessibilityNodeInfo n = findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
if (n != null && n.isEditable()) return n;
for (AccessibilityWindowInfo w : getWindows()) {          // 跨 App 必须走这条
    AccessibilityNodeInfo f = w.getRoot().findFocus(FOCUS_INPUT);
    if (f != null && f.isEditable()) return f;
}
```

只调 `findFocus` 找不到别的 App 里的输入框，必须遍历窗口。

### 2. `isEditable()` 判据

找到焦点节点还不够，它可能是个不可编辑的容器。用 `isEditable()` 过滤。

### 3. 读回前重新找一次焦点

`ACTION_SET_TEXT` 之后手上的 `node` 可能已过期，
延迟 400ms 再 `findFocusedInput()` 读一次才靠得住。

---

## 已知边界

1. **动态注册接收器必须声明 EXPORTED / NOT_EXPORTED**（API 33+）。
   v1 没声明，`onServiceConnected` 直接抛
   `SecurityException: One of RECEIVER_EXPORTED or RECEIVER_NOT_EXPORTED
   should be specified...`，表现是"textin refapp keeps stopping"，
   而 `dumpsys` 里服务看着是绑上的。
2. **`RECEIVER_EXPORTED` 让广播可被本机任何进程触发。** 这是参考实现的取舍——
   触发方是 `adb shell am broadcast`（外部来源），必须 EXPORTED。
   一个**不**对 adb 开放的实现应该用 `RECEIVER_NOT_EXPORTED` + 显式组件名。
3. **没有认证。** 同 §2——参考实现不暴露网络面，所以不需要。
4. **只覆盖"整段替换"语义**，未测光标不在末尾、只读字段、输入法联想交互。
5. **未在其他 ROM 上验证。** 取证来自 AVD Android 15 / Google APIs。

---

## 适用范围

**本库定位**：代码 400 行、无网络面、无第三方应用依赖、
Apache-2.0。作为「怎么在公开 API 边界内把文本送进任意输入框」的
最小可运行范例，对同类 agent 项目有直接参考价值。

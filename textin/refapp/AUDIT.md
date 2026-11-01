# refapp 审计说明 · D2 备料

> 本文说明这个参考实现调用了什么、要哪些权限、如何撤销。
> 本文的目标：让读者**不需要读代码**即可判断这个 App 接触了什么。
>
> 所有事实均从文件提取，非记忆。可复跑的取证命令附在每条后面。

## 一、基本事实

| 项 | 值 |
|---|---|
| 包名 | `com.textin.refapp` |
| 版本 | versionCode 1 / versionName 0.1.0 |
| 源码规模 | 2 个 Java 文件 393 行 + 1 个 manifest + 3 个 res 文件 |
| 组件 | 1 个 Activity（`.MainActivity`）+ 1 个 Service（`.SetTextService`） |
| 构建 | `build.sh`（aapt2 + javac + d8 + zipalign + apksigner，无 Gradle） |

```bash
wc -l src/com/textin/refapp/*.java          # 78 + 315 = 393
grep -o 'android:name="[^"]*"' AndroidManifest.xml
```

## 二、权限清单（**零权限**）

```bash
grep -c 'uses-permission' AndroidManifest.xml   # 0
grep -c 'INTERNET' AndroidManifest.xml          # 0
```

**这个 App 不声明任何 `uses-permission`。** 没有 `INTERNET`、没有存储、
没有网络状态、没有查询全部应用。

唯一的保护级声明是 Service 上的：

```xml
android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE"
```

这是 Android **强制要求**的——只有系统能绑定 AccessibilityService，
第三方 App 无法直接 bind。这是官方模式，不是本项目的选择。

## 三、它接触什么

| 能力 | 来源 | 用户同意点 |
|---|---|---|
| 读焦点输入框状态 | `AccessibilityService` | 系统设置 → 无障碍 → 手动开启 `textin refapp` |
| 枚举窗口（含 IME） | `flagRetrieveInteractiveWindows` | 同上，随无障碍授权一并生效 |
| 写入文本 | `AccessibilityNodeInfo.performAction(ACTION_SET_TEXT)` | 同上 |
| 读结果 JSON | 应用私有目录 应用私有目录下的 last_result.json（运行时产物，不在仓库中） | 需 `adb shell run-as`（App 是 debuggable） |

**撤销路径**：系统设置 → 无障碍 → 关闭 `textin refapp`。服务立即停止，
不再接收任何事件。**这是系统级撤销，不依赖 App 自己配合。**

**降级行为**：无障碍关闭时服务不启动，广播无人接收，
`am broadcast` 静默返回（无结果文件）。失败是可见的、不是静默的。

## 四、四个读者会问的点（我主动列出，含我的判断）

### ① `android:debuggable="true"`

**为什么需要**：结果通过 `adb shell run-as com.textin.refapp cat files/last_result.json`
读取，`run-as` 要求 debuggable。这是参考实现读取结果的唯一途径——
不引入 HTTP 服务、不引入存储权限。

**取舍**：debuggable App 不应上生产。**这是参考实现，不是产品。**
若读者要求，可以改成把结果写进 `Log.i` 由 `adb logcat` 读，代价是结果格式不可结构化。

**我的建议**：保留 debuggable，但 README 已明确「仅供本机验证」。

### ② `RECEIVER_EXPORTED` —— **真实攻击面，必须说明**

三个 receiver 全部用 `Context.RECEIVER_EXPORTED` 注册
（API 33+ 不显式声明会直接抛 `SecurityException`）。

**含义**：同设备上**任何其他 App** 都能
`sendBroadcast(new Intent("com.textin.refapp.SET_TEXT").putExtra("text_b64", ...))`
让这个 App 往当前焦点输入框写任意文本。

**为什么这样写**：触发源是 `adb shell am broadcast`（见 `../SPEC.md` §6），
adb 下发的广播走的就是外部路径。

**缓解现状**：**无**。参考实现没有加调用方白名单。

> 注：这个取舍**已经在 `README.md` 已知边界② 写明**
> （「`RECEIVER_EXPORTED` 让广播可被本机任何进程触发。这是参考实现的取舍」）。
> 本文的作用是把它从「一条边界」提升为「读者会问的点」，
> 并给出三种收紧方案。

**我的判断**：这是参考实现的**已知简化**，不是缺陷——
但它必须被写下来，否则读者会在代码里自己发现，
那时性质就从「已知简化」变成「隐瞒」。

**若要收紧**（3 种，从轻到重）：
1. `registerReceiver` 加 `permission` 参数，要求调用方持有一个 signature 级权限
2. receiver 里校验 `intent.getPackage()` 或调用方 UID 是否在预期集合内
3. 完全不用广播，改用 `adb shell am start-service` + 显式 Intent 到本包组件

**我的建议**：采用方案 3 最干净——**显式 Intent 指向本包组件，
外部 App 无法伪造包名**，且仍然只需 adb 触发。

### ③ `service android:exported="true"`

`exported="true"` 但**同时**声明了 `BIND_ACCESSIBILITY_SERVICE` 权限，
所以实际只有系统能绑定。这是 AccessibilityService 的标准声明方式，
`exported` 不可省（否则系统无法绑定）。**不是暴露面。**

### ④ 无网络面

`grep -c INTERNET AndroidManifest.xml` = **0**。
没有 `ServerSocket`、没有 `HttpURLConnection`、没有 `WebSocket`。
`SetTextService.java` 的类注释写明了为什么不用 HTTP：

> 这是**参考实现**，要展示的是「SET_TEXT 这条路走得通」，
> 不是「怎么把设备暴露到网络上」。加 HTTP 服务会让最小样例变成一个网络服务，
> 超出参考实现的范围。

## 五、构建与签名

```bash
# keystore 缺失时自动生成（if [ ! -f "$KS" ]）
grep -A3 'if \[ ! -f "\$KS" \]' build.sh
```

- keystore 放在 `build/` **外面**（`.debug.keystore`），避免 `rm -rf build`
  每次换 key。这是 的教训：换 key 后 `adb install -r` 报
  `INSTALL_FAILED_UPDATE_INCOMPATIBLE`，而 `| tail -1` 会把这行吞掉，
  导致**拿着旧 APK 测新代码**
- `.debug.keystore` **绝不入库**（`.gitignore` 已加 `*.keystore` / `*.jks`）
- 读者 clone 后 `./build.sh` 会生成自己的 debug key，不影响验证

## 六、命名纪律自查

| 检查项 | 结果 |
|---|---|
| 是否点名任何第三方应用 | ❌ 无（`strings.xml` 全量检查） |
| 是否以「用户不方便时的场景化辅助」为框架 | ⚠️ 部分——README 用「把文本写入当前焦点输入框」的技术框架，未做场景化包装 |
| 是否走系统公开能力 | ✅ AccessibilityService + `ACTION_SET_TEXT`，全部公开 API |

**`svc_desc` 现状**：
> 演示用无障碍服务：把文本写入当前焦点输入框。仅本机使用。

这一句是技术描述，**不含任何应用名、不含任何「操控」字样**，符合纪律。

## 七、结论（备料意见，非决定）

**技术上具备提交条件**：零权限、无网络面、撤销走系统级、命名合规。

**唯一需要读者裁决的是 ② `RECEIVER_EXPORTED`**。
我建议提交前先落方案 3（显式 Intent 到本包组件）——约 10 行改动，
能把「任何 App 都能触发」收紧成「只有 adb 能触发」，
与参考实现的定位（本机验证工具）一致。

#!/usr/bin/env bash
# textin/refapp —— 最小 SET_TEXT 参考实现的构建脚本。
#
# 产出：build/textin-refapp.apk（debug 签名，仅供本机验证）
#
# 前置：Android SDK（platforms/android-35 + build-tools）+ JDK
#
# 用法：./build.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SDK="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
BT="$SDK/build-tools/35.0.0"
PLATFORM="$SDK/platforms/android-35/android.jar"
OUT="$HERE/build"
PKG="com.textin.refapp"

[ -x "$BT/aapt2" ] || { echo "❌ 找不到 aapt2：$BT/aapt2"; exit 1; }
[ -f "$PLATFORM" ] || { echo "❌ 找不到 android.jar：$PLATFORM"; exit 1; }

# ★ keystore 放在 build/ **外面**。
#   v1 把 keystore 放 build/ 里、开头又 `rm -rf build`，
#   于是每次构建都换一把新 debug key，`adb install -r` 报
#     INSTALL_FAILED_UPDATE_INCOMPATIBLE: signatures do not match
#   而 `install -r ... | tail -1` 把这行吞了，我拿着**旧 APK** 测新代码，
#   得出"修复没生效"的假结论。**构建系统的失败也是装置的失败。**
rm -rf "$OUT"; mkdir -p "$OUT/gen" "$OUT/obj" "$OUT/dex"

echo "== 1/6 编译资源 =="
"$BT/aapt2" compile --dir "$HERE/res" -o "$OUT/res.zip"

echo "== 2/6 链接资源 + 生成 R.java =="
# ★ min/target SDK 必须显式给。v1 没给，装的时候报
#   INSTALL_FAILED_DEPRECATED_SDK_VERSION: must target at least SDK 24, but found 0
#   ——aapt2 link 不写这两个属性时，系统读到的 targetSdk 是 0。
"$BT/aapt2" link -o "$OUT/app.apk" \
  -I "$PLATFORM" \
  --manifest "$HERE/AndroidManifest.xml" \
  --min-sdk-version 26 --target-sdk-version 35 \
  --java "$OUT/gen" \
  "$OUT/res.zip"

echo "== 3/6 编译 Java =="
find "$HERE/src" "$OUT/gen" -name '*.java' > "$OUT/sources.txt"
# ★ 不用 --boot-class-path：JDK 9+ 且 target>=9 时该选项被禁。
#   android.jar 放 -classpath 即可——android.* 从它来，java.* 从 JDK 平台来。
# ★ 不用 `|| true` 吞错误：v1 就因为吞了 javac 的报错，
#   d8 拿到空目录、zip 报 "Nothing to do!"，整条链静默失败。
javac -nowarn -encoding UTF-8 -classpath "$PLATFORM" \
  -d "$OUT/obj" @"$OUT/sources.txt"

echo "== 4/6 dex =="
"$BT/d8" --release --min-api 26 --lib "$PLATFORM" \
  --output "$OUT/dex" $(find "$OUT/obj" -name '*.class')
[ -f "$OUT/dex/classes.dex" ] || { echo "❌ d8 没产出 classes.dex"; exit 1; }

echo "== 5/6 打包进 apk =="
cd "$OUT"
cp app.apk unsigned.apk
zip -q -j unsigned.apk dex/classes.dex
"$BT/zipalign" -f 4 unsigned.apk aligned.apk

echo "== 6/6 签名（debug keystore，仅供本机验证） =="
KS="$HERE/.debug.keystore"
if [ ! -f "$KS" ]; then
  keytool -genkeypair -v -keystore "$KS" -storepass android \
    -keypass android -alias androiddebugkey -keyalg RSA -keysize 2048 \
    -validity 10000 -dname "CN=textin,O=textin,C=US" 2>/dev/null
fi
"$BT/apksigner" sign --ks "$KS" --ks-pass pass:android \
  --key-pass pass:android --out "$OUT/textin-refapp.apk" aligned.apk

echo ""
echo "✅ 构建完成：$OUT/textin-refapp.apk"
echo "   包名：$PKG"
echo "   安装：adb -s emulator-5554 install -r $OUT/textin-refapp.apk"

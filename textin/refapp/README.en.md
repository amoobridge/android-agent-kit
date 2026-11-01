# textin/refapp · Minimal `ACTION_SET_TEXT` reference implementation

**[English](README.en.md)** · **[中文](README.md)**

**License** Apache-2.0 · **Date** 2026-10-27

---

<a id="english"></a>

## English

### What it is

A minimal reference implementation of `ACTION_SET_TEXT` over an accessibility
service — the path that survives shell metacharacters, spaces and non-ASCII,
where `adb shell input text` does not.

Audit: [`AUDIT.md`](AUDIT.md)

### Why it exists

`textin` measures that `adb shell input text` works for only 4 of 19 input
classes, and that backticks are **executed as a command**. This app is the
smallest thing that demonstrates the alternative, so the claim is checkable
rather than asserted.

### Verified on a real device

Same inputs, same field, same clearing procedure, only the write step differs:
**A path 4/19, B path 19/19.**

| | `adb shell input text` | `am broadcast --es text_b64` → SET_TEXT |
|---|---|---|
| spaces | `hello world` → `hello` | ✅ complete |
| Chinese / emoji | no change + NPE | ✅ complete |
| **backticks** | `` a`b`c `` → `ac` (**`b` executed**) | ✅ verbatim |
| `;` `\|` `&` | → `a` | ✅ verbatim |
| quotes / parens | no change + sh syntax error | ✅ verbatim |

**Two layers must be proven separately**: base64 guarantees the text reaches the
Bundle unchanged; `performAction` guarantees it lands in the field unchanged.
Passing text directly with `--es` reproduces the `input text` failure exactly,
because `am broadcast` also goes through the device-side shell.

### What this app is not

It is a **reference implementation, not a bridge**. No HTTP service, no token, no
listening socket, no root. Two Java files, a build script, and a README.

| Check | Result |
|---|---|
| `uses-permission` count | **0** |
| `INTERNET` permission | **0** |
| Network surface | no `ServerSocket`, `HttpURLConnection`, `WebSocket` |
| Revocation | system settings → accessibility → off (**system-level; does not depend on app cooperation**) |
| Degradation | service not started → broadcast silently produces no result file (**visible failure**) |

### The one point a reviewer must decide

**`RECEIVER_EXPORTED`.** All three receivers register with it — mandatory on
API 33+, otherwise `SecurityException` — which means any app on the device can
trigger a write. Three ways to tighten it are listed in `AUDIT.md`; the
recommended one is an explicit Intent targeting this package's own component,
which external apps cannot forge.

### Four engineering notes found on a real device

1. Dynamically registered receivers on API 33+ **must** declare
   `RECEIVER_EXPORTED`, or `onServiceConnected` throws `SecurityException` while
   `dumpsys` still shows the service as bound.
2. After reinstalling, `enabled_accessibility_services` goes stale — the service
   returns to `Bound services: {}` and no amount of broadcasting helps. The build
   script checks for this and refuses to report a conclusion.
3. `--boot-class-path` is rejected on JDK 9+ / target ≥ 9.
4. **A keystore inside `build/` plus `rm -rf build` means a new key every
   build** → `install -r` reports a signature mismatch, and `| tail -1` swallows
   the line → **you end up testing the old APK and concluding your fix did
   nothing.**

> A build system's failure is also an apparatus failure.

### Build and run

```bash
cd textin/refapp
./build.sh          # needs JDK + Android SDK; keystore is generated if absent
adb install -r build/refapp.apk
# then enable the accessibility service in system settings
```

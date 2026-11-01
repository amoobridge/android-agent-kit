# textin · How to actually get text into an Android input field

**[English](README.en.md)** · **[中文](README.md)**

**License** Apache-2.0 · **Version** 0.1.0 · **Date** 2026-10-27
**Test environment** AVD `avd-api35` (Android 15 / Google APIs / arm64-v8a)

---

<a id="english"></a>

## English

### What it is

Forensics of text input on Android: which inputs survive
`adb shell input text`, and an alternative path that survives all of them.

Shell metacharacters are executed on-device, spaces truncate silently, and
non-ASCII throws — all with misleading exit codes.

### Why it exists

GELab-Zero's code carries the evidence of how hard this is:

- `mobile_action_helper.py:600` has `adb shell input text` **commented out**,
  replaced by yadb (push a jar to `/data/local/tmp`, start a Java process via
  `app_process`, and require the keyboard to already be up)
- `pu_frontend_executor.py:84-88` carries the remains of a
  `value.replace(" ", "_")` escape — **also commented out**

Two generations of implementation, both abandoned. That is a strong signal.

### Measured: 4 of 19 input classes work

| Class | Count | Behaviour |
|---|---|---|
| Clean | 4 | `hello` / `a#b` / `a*b?` / `x`×200 |
| Space truncation | 3 | **exit code 0, silent.** `hello world` → `hello` |
| Non-ASCII | 2 | **exit code 255 + NPE** — the easiest to handle, because it is loud |
| Shell metacharacters | 8 | `` a`b`c `` → `ac`, with **`b` executed as a command** |
| Escape sequence itself | 2 | `a%s` → `a ` (`%s` is adb's own space escape) |

The critical point: `subprocess` is called with an argument list and **never
passes through the local shell** — and it still fails. `adb shell <cmd>` is
equivalent to `/system/bin/sh -c <cmd>` **on the device**. There is a second
shell layer you do not control. The backtick row is an injection surface, not
just data corruption.

### The three-way classification

The backtick row does not fit a binary pass/fail split. It returns exit code 0
(so "succeeded") while `b` really was executed as a command. Spec condition C6
therefore classifies into **three** kinds:

| Kind | Signal | Count |
|---|---|---|
| Silent | rc = 0 **and** stderr empty | 6 |
| **Third kind** | rc = 0 **but** stderr non-empty | **1** |
| Loud | rc ≠ 0 | 8 |

The third kind deserves its own bucket precisely because it *has* a signal —
just on the side that is easy to ignore.

### The alternative: accessibility `ACTION_SET_TEXT`

Verified on a real device: **19 / 19** for the same inputs, the same field, the
same clearing procedure — only the write step differs.

| | `adb shell input text` | `am broadcast --es text_b64` → SET_TEXT |
|---|---|---|
| spaces | `hello world` → `hello` | ✅ complete |
| Chinese / emoji | no change + NPE | ✅ complete |
| **backticks** | `` a`b`c `` → `ac` (**`b` executed**) | ✅ verbatim |
| `;` `\|` `&` | → `a` | ✅ verbatim |
| quotes / parens | no change + sh syntax error | ✅ verbatim |
| `%s` / backslash / leading-trailing space | `a ` / `ab` / `pad` | ✅ verbatim |

**The transport layer must be proven too.** The first version passed text
directly with `--es text "a\`b\`c"` and read back `ac` — identical to the
`input text` failure. That was not SET_TEXT's fault; `am broadcast` also goes
through the device-side shell. Two things must be shown separately:

```
transport (base64)   guarantees the text reaches the Bundle unchanged
API (SET_TEXT)       guarantees the text lands in the field unchanged
```

### `text == ""` is the wrong emptiness test

When a field is empty, the dump's `text` attribute reports the **hint**:

```
text = "Search settings"     <- the field is empty
```

`text == ""` therefore cannot be used to decide a field is empty. See
`fieldstate` for the full four-predicate treatment.

### refapp: minimal reference implementation

`refapp/` is a minimal accessibility service that receives text over a broadcast
and writes it with `ACTION_SET_TEXT`.

| Check | Result |
|---|---|
| `uses-permission` count | **0** |
| `INTERNET` permission | **0** |
| Network surface | no `ServerSocket`, `HttpURLConnection`, `WebSocket` |
| Revocation | system settings → accessibility → off (**system-level, does not depend on app cooperation**) |
| Degradation | service not started → broadcast silently produces no result file (**visible failure**) |

The one point a reviewer must decide: **`RECEIVER_EXPORTED`**. All three
receivers use it (required on API 33+, otherwise `SecurityException`), which
means any app on the device can trigger a write. `refapp/审计表.md` lists three
ways to tighten it.

### Verify

```bash
cd textin && python3 -m pytest tests/ -q
```

Real-device reproduction needs an AVD; see `textin/refapp/README.md`.

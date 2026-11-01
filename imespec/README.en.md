# imespec · Keyboard occlusion and element reachability

**[English](README.en.md)** · **[中文](README.md)**

**License** Apache-2.0 · **Version** 0.1.0 · **Date** 2026-10-27
**Test environment** AVD `avd-api35` (Android 15 / Google APIs / arm64-v8a)

---

<a id="english"></a>

## English

### What it is

Decide whether an element is actually reachable while the on-screen keyboard is
up.

The IME is a separate window that `uiautomator dump` never captures, and the app
window does not shrink to make room for it.

### Measured on a real device

Settings app, search field containing `net`, keyboard up:

| | Value |
|---|---|
| IME window | `type=2`, `English (US) (QWERTY)`, bounds `0 1517 1080 2400` |
| Share of screen | **36.8%** |
| XML nodes | 35, package **all belonging to the app** |
| Keyboard nodes in XML | **0** |
| App window bounds | still `0 0 1080 2400` (**did not shrink**) |
| Clickable elements | 13 |
| Fully occluded | **4** |
| Partially occluded | **1** |
| **Unreachable** | **5 / 13 = 38.5%** |

An agent that wants to tap a list item near the bottom (y ≈ 2017) hits the
keyboard. **No exception, no error — the tap "succeeded."**

### Design principle

> **Without keyboard information, report `unknown`. Do not guess.**

Guessing "no keyboard" makes the agent tap air; guessing "keyboard present"
rejects valid taps. Both are wrong, so the library refuses to answer.

### Identify the IME by type, not by title

The title changes with the input method (`简体中文拼音`, `English (US)`, …).
The criterion is `type == TYPE_INPUT_METHOD (2)`. A dedicated golden vector tests
exactly this.

### A negative finding worth recording

`AccessibilityService` has **no** IME state accessor.
`InputMethodManager.isAcceptingText()` is not available inside that service's API
(and is deprecated on API 33+). **The public accessibility API offers no direct
query for "is the keyboard up"** — the only route is indirect, through the window
list. Recorded in the comment of `refapp`'s `reportWindows()`.

### Implementation note

Parsing bounds needs care: `['0,1548','1080,1712]` puts the comma *inside* the
number, so `int('0,1548')` raises. An early version of the parser got this wrong
and concluded "there are no occluding nodes" — **which nearly cost us the entire
38.5% finding**. Spec condition C6 and a dedicated vector now pin this down.

### Verify

```bash
cd imespec && python3 -m pytest tests/ -q
```

Real-device evidence is committed under `data/`; `TestRealEvidence` recomputes
from it.

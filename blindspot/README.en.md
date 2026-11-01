# blindspot · The window that `uiautomator dump` never sees

**[English](README.en.md)** · **[中文](README.md)**

**License** Apache-2.0 · **Version** 0.1.0 · **Date** 2026-10-27
**Test environment** AVD `avd-api35` (Android 15 / Google APIs / arm64-v8a)

---

<a id="english"></a>

## English

### What it is

Reconcile `screencap` and `uiautomator dump` to expose elements that exist in XML
but are unreachable on screen.

Elements reported as clickable can be covered by the keyboard; tapping them
writes into a text field instead of hitting the target.

### Why it exists

The dominant assumption in Android GUI automation is that the XML dump
represents the screen. It does not — and the mismatch is not an edge case.

### The decisive evidence

Settings app, search field containing `net`, keyboard up:

| | `screencap` | `uiautomator dump` |
|---|---|---|
| size | 1080 × 2400 | 35 nodes |
| keyboard | **present**, y ≥ 1517 | **zero nodes** |
| keyboard top edge | y = 1517 | — |
| agreement with IME bounds | **exactly equal** | — |
| app window | — | still `0 0 1080 2400` (**did not shrink**) |

Row-by-row colour sampling of the screenshot: y = 1500 is app background
`rgb(232,231,239)`, y = 1509–1516 is a 16 px shadow gradient, and **from y = 1517
it is keyboard background `rgb(241,240,247)`**. The keyboard's top edge matches
the `AccessibilityWindowInfo` IME bounds exactly.

**The behavioural test.** Tapping the centre of the node XML reports as
`clickable=true` at `[0,1935][1080,2158]`, i.e. `(540, 2017)`, changed the search
field from `net` to **`netv`**. The tap landed on the keyboard's `v` key and
**wrote data into the app**; the XML-declared target was never triggered.

This is not merely "nothing happened" — it is **silent state pollution**. And an
agent that only checks "did the screen change" will see a change and may conclude
the tap worked.

### The numbers

Of 13 `clickable=true` nodes, **5 overlap the keyboard** (4 at 100%, 1 at 18.9%)
— **5/13 unreachable, 38.5%**.

### Root cause

1. The IME is an independent window; `uiautomator dump` captures only the active
   app window
2. The app window does not shrink (`adjustPan` in this environment), so bounds
   are unchanged and the occlusion is invisible
3. `screencap` captures the whole screen, so the keyboard *is* in the screenshot

**The screenshot says there is a keyboard; the XML says there is a clickable
element.** One of them is wrong, and it is the XML.

### Design principles

- **The screenshot is the reference channel; the XML is the derived channel. On
  conflict, the XML is wrong.**
- **With no screenshot, `screenshot_agrees` reports None. Never pretend to have
  verified.**
- **Window types not verified here (toast, system permission dialogs, the
  notification shade) are not added to the blind-region set by speculation** —
  doing so would manufacture a new false criterion.

### Verify

```bash
pip install -r ../../requirements.txt    # Pillow optional; 2 tests skip without it
cd blindspot && python3 -m pytest tests/ -q
```

`TestRealEvidence` recomputes from the committed real-device dumps, so the spec
and the implementation cannot drift apart unnoticed.

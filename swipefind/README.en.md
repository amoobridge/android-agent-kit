# swipefind · Validity and absorption of swipe gestures

**[English](README.en.md)** · **[中文](README.md)**

**License** Apache-2.0 · **Version** 0.1.0 · **Date** 2026-10-27
**Test environment** AVD `avd-api35` (Android 15 / Google APIs / arm64-v8a)

---

<a id="english"></a>

## English

### What it is

Validity and absorption rules for swipe gestures.

A swipe that starts on the keyboard writes into the focused field instead of
scrolling, and the working distance range is not monotonic.

### Finding 1: a swipe starting on the keyboard writes text (3 / 3 reproduced)

Settings app, search field containing `net`, keyboard up:

| Gesture | Field change |
|---|---|
| vertical swipe in keyboard area (540,2000)→(540,1000) | `net` → **`net by`** |
| diagonal swipe in keyboard area (700,2100)→(380,1200) | `net` → **`net be`** |
| short swipe in keyboard area (540,1900)→(540,1600) | `net` → **`net gt`** |
| **control · swipe in app area** (540,1400)→(540,400) | `net` → `net` ✅ |

**A scroll gesture silently writes 2–3 characters into the input field.**

This is the gesture version of the `blindspot` tap finding, and worse: a tap
writes one character, a swipe writes several. The criterion is the **start
point** being inside the keyboard, not the path intersecting it.

### Finding 2: distance is not monotonic

Fixed 250 ms, varying only distance: 100 px ❌ · 300 px ❌ · 600 px ✅ · 900 px ✅ ·
**1200 px ❌** · **1500 px ❌**

**Not "longer is better."** There is a sweet spot, and beyond it the gesture fails
silently too.

### A methodology trap that produced two wrong conclusions

`reset_home()` (`am start -a android.settings.SETTINGS` + `KEYCODE_BACK`) does
**not** reset the scroll position. It made me conclude two false things:

- Experiment 1: "below 200 ms nothing works at all" — an artefact of the threshold
- Experiment 3: "scrolling too far is unrecoverable, restored = 0 / 6"

After switching to the HOME key for reset: 200 ms works, and scrolling down 3 +
up 3 restores 18 of 22.

> **The reset itself needs a criterion. Otherwise the apparatus's failure gets
> reported as the subject's failure.**

### Derived semantics

- `is_exhausted(history, n)` — a stop condition for agents
- `effect(target_ref)` — four verdicts plus overlay detection
- `is_loading()` — distinguishes "still rendering" from "nothing changed"

### Known boundaries

1. Exhaustion data has only one 0-step sample; the spec's `window = 2` requires
   two steps, so the spec is deliberately conservative here and a test pins the
   difference.
2. The gesture path must be clipped as a **line segment against the keyboard
   rectangle** (Liang–Barsky). Using the endpoints as polygon corners gives a
   zero-width bounding box for vertical paths, so "path crosses the keyboard" is
   always false.

### Verify

```bash
cd swipefind && python3 -m pytest tests/ -q
```

Real-device evidence is committed under `data/`.

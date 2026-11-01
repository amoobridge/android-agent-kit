# screendiff · Screen-change semantics between two snapshots

**[English](README.en.md)** · **[中文](README.md)**

**License** Apache-2.0 · **Version** 0.1.0 · **Date** 2026-10-27
**Test environment** AVD `avd-api35` (Android 15 / Google APIs / arm64-v8a)

---

<a id="english"></a>

## English

### What it is

Screen-change semantics between two snapshots:
matched / added / removed / moved / state / label.

Position-wise comparison reports everything as changed after a scroll, hiding
the one element that actually changed.

### Why it exists

The mainstream approach compares element lists position by position. That fails
systematically on Android:

- **Scroll**: `ref`s are positional, so a scroll misaligns everything. Position-wise
  comparison reports "9 of 11 elements changed" when the truth is **9 shifted,
  0 added, 0 removed**.
- **Insert at top**: position-wise comparison marks *every* element as changed, and
  the one genuinely new element is buried in noise.

Both directions destroy the signal an agent needs.

### Measured on a real device (system settings)

| Scenario | matched | added | removed | moved | state | label |
|---|---|---|---|---|---|---|
| airplane mode on (**single element changed**) | 11 | 0 | 0 | 0 | **1** | **1** |
| list scrolled up (**pure shift**) | 11 | 0 | 0 | **9** | 0 | 0 |

Row 1 is the precision evidence; row 2 is the value evidence. `effect()` on the
same scenarios gives: `e3` target_changed(label) / `e4` target_changed(state) /
`e5` target_unchanged.

### The matching algorithm was corrected twice by real data

This is not a paper design — the algorithm was wrong twice before the real dumps
corrected it.

1. **Full-screen containers swallow small elements.** The settings home scroll
   container has bounds `[0,74][1080,2337]`, giving an overlap ratio ≥ 0.8 with
   *any* element on the page. Pure geometric tier-1 matching matched "avatar
   image" to the new page's scroll container and reported "the avatar became a
   scroll container". → An area-ratio gate was added: `min/max ≥ 0.5`.
2. **Empty `class_name` counted as "same class".** Two anonymous elements with
   empty class names were treated as the same class and matched on geometry
   alone. → All three identity tiers now require the field to be non-empty.

Both have regression tests.

### API

```python
d = diff(prev_snap, cur_snap)
d.matched        # [(prev_index, cur_index)]
d.added / d.removed / d.moved
d.state_changed  # refs whose enabled/checked/selected changed
d.label_changed  # refs whose label changed
```

### Known boundaries

1. **Cross-page matching is not trustworthy.** On a real page transition,
   screendiff reported `matched 8` where **all 8 had different labels** — a
   false-match rate of 100%. See `crosstrack` for the audit layer that exposes
   this.
2. `Element` is a value object; sorting pairs must carry explicit indices, not
   use `list.index()`.

### Verify

```bash
cd screendiff && python3 -m pytest tests/ -q
node js/conformance.js    # 27 golden vectors, independent JS implementation
```

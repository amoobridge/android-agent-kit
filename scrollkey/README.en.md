# scrollkey · Content-derived stable keys across scrolling

**[English](README.en.md)** · **[中文](README.md)**

**License** Apache-2.0 · **Version** 0.1.0 · **Date** 2026-10-27
**Test environment** AVD `avd-api35` (Android 15 / Google APIs / arm64-v8a)

---

<a id="english"></a>

## English

### What it is

Content-derived stable keys for UI elements that survive scrolling.

Element refs are positional indices; scrolling reassigns them even when the row
itself did not change.

### Why it exists

`提案/03-stale-ref` closes the invalidation gap by rejecting stale references.
But that leaves a real cost: **after every scroll, every reference is void**, and
a re-dump is required. This library attacks the cost directly — give each element
a key derived from its *content* so the same row keeps the same key across
scrolls.

### Measured on a real device (5-frame scroll sequence)

Each adjacent pair shares 9 rows:

| Transition | Shared rows | Ref changed |
|---|---|---|
| s0 → s1 | 9 | 9 |
| s1 → s2 | 9 | 7 |
| s2 → s3 | 9 | 7 |
| s3 → s4 | 9 | 7 |
| **total** | **36** | **30 (83%)** |

Tracking one row, "Sound & vibration": its ref goes `e11 → e9 → e6 → e4` while
its key is the same string across all four frames.

### The most important self-correction

I initially wanted to advertise this as "saves you a re-dump". **Writing the spec
is what exposed that as wrong**: to click by key you still need the current
snapshot, `resolve_key` → get the ref → take the bounds. **The dump still has to
happen.**

The value of a key is **maintaining referential continuity across frames**, not
avoiding re-observation. This is now boundary ① in the spec, with
`test_key_does_not_save_redump` pinning it down.

### Key derivation

```
rid:  <resource-id>                          when present and non-structural
lbl:  <class>|<normalised label>[:<ordinal>]  otherwise
anon: <class>[:<ordinal>]                    when there is no label at all
```

Structural ids (those naming containers rather than content) are excluded — they
carry no semantics for the model.

### Known boundaries

1. **A key does not save the re-dump** — the most easily misunderstood point
2. **The ordinal is only stable while the sibling group is unchanged** — inserting
   a row earlier shifts later ordinals. Same *kind* of problem as refs, but the
   blast radius is far smaller (only same-label rows, not the whole page)
3. **A changed label is a changed key** — a deliberate choice: being explicit is
   safer than hiding it
4. **Keys for anonymous elements are weak** — one `class` filter above nothing

### Real data, honestly stated

Across 16 real screens and the 5-frame scroll sequence, **132+ elements, zero
base-key collisions**. But the spec explicitly says **this must not be cited as
"Android UIs have no collisions"** — the sample happens to have unique labels.
The collision-resolution logic is therefore covered by **synthetic vectors**:
real data with no collisions is precisely the case that gives no criterion for
the most bug-prone part.

### Verify

```bash
cd scrollkey && python3 -m pytest tests/ -q
```

Real-device dumps are committed under `data/`.

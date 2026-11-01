# crosstrack · Trust levels for cross-page element tracking

**[English](README.en.md)** · **[中文](README.md)**

**License** Apache-2.0 · **Version** 0.1.0 · **Date** 2026-10-27
**Test environment** AVD `avd-api35` (Android 15 / Google APIs / arm64-v8a)

---

<a id="english"></a>

## English

### What it is

Trust levels for element tracking across screens, with an explicit false-match
rate.

Geometric matching across pages produces confident nonsense that looks perfectly
reasonable in the numbers.

### The real accident

`screendiff.diff(home1, sub1)` reports `matched 8, added 2, removed 3`.

**All 8 of those matches have different labels:**

| prev (home) | cur (notification sub-page) |
|---|---|
| Network & internet · Mobile, Wi-Fi… | App notifications · Control… |
| Apps · Assistant, recent apps… | Conversations · No priority… |
| Storage · 51% used | Notifications on lock screen · Hide… |

`matched 8` **looks entirely reasonable**, and a caller has no way to know all 8
are garbage. This is the first item on screendiff's own boundary list (full-screen
containers overlap heavily with everything) showing up in the cross-page case.

### Two further findings

**① `snapshot_id` is a perfect same-screen discriminator** — `home1`, `home2` and
`home3` are three separate entries into the same home page and their ids are
**identical**. **But the converse does not hold**: scrolling also changes the id,
so an id mismatch only means "the content changed", not "the page changed".

**② The cross-page key intersection is empty** — `shared_keys(home1, sub1)`
returns `set()`. That *is* the set of elements two screens genuinely share.

### Design: do not fix screendiff, add an audit layer

Per the incremental principle, `audit_diff` does not change screendiff's
behaviour. It relabels the matches screendiff already computed, by identity tier:

| Comparison | screendiff as-is | after audit |
|---|---|---|
| home1 vs sub1 | matched 8 | justified **0** / geometric_only **8** / **false_match_rate 100%** |
| sub1 vs sub2 | matched 10 | justified 9 / geometric_only 1 / 10% |

**Silent false matches become an explicit number.**

### Trust tiers, strongest first

`rid` > `label_class` > `class` > `anon_class` > `none`

The tiers **descend step by step**: a match that keeps its class but changes its
label lands on `anon_class`, not `none`. The point is not that it equals `none` —
it is that it is **not trustworthy**.

### Known boundaries

1. `snapshot_id` is not a page-change criterion.
2. Anonymous elements are never trustworthy across pages (a conservative false
   rejection when on the same screen).
3. The audit is an overlay, not a fix.
4. A label change is judged untrustworthy — correct across pages, over-conservative
   on the same screen. For same-screen questions use screendiff's `effect()`.

### Verify

```bash
cd crosstrack && python3 -m pytest tests/ -q
```

Real-device dumps are committed under `data/`; tests recompute from them.

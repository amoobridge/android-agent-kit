# screenpoint · Deterministic coordinate inverse mapping

**[English](README.en.md)** · **[中文](README.md)**

**License** Apache-2.0 · **Version** 0.1.0 · **Date** 2026-10-27

---

<a id="english"></a>

## English

### What it is

Deterministic inverse mapping from model coordinates back to device pixels.

The one deterministic step in the coordinate chain should not be delegated to
the model.

### Why it exists

A GUI agent works on a downscaled screenshot and gets coordinates back from a
model. Turning those coordinates back into device pixels is **pure arithmetic** —
yet the mainstream approach writes it into the prompt:

> *"multiply its x by 1.5 and y by 1.5"*

That converts the only deterministic link in the entire chain into a
probabilistic one. `mobile-mcp`'s `coordinate-mapping.ts` does exactly this, and
its ratio is additionally pre-rounded to three decimal places
(`RATIO_DECIMALS = 3`), which on a 4000 px screen is a **2.0 px** error, not the
"at most 0.5 px" one might assume.

This library does the inverse in code and ships a standard data format
(scaled screenshot + mapping metadata) so the mapping is auditable.

### Verified on a real device

**648,000 pixels, point-for-point exact hit** (1080 × 600 region, every mapped
pixel checked).

### The resampling phase convention

This is the subtle part, and it is a genuine trap.

PIL's `resize(NEAREST)` samples at phase `(i + 0.5) · s`, while the inverse
convention is `i · s`. **They differ by half a source pixel**, so at image edges
they disagree by 1 px.

The first version of the verification therefore reported **17,353 mismatches
(2.7%)**, all concentrated on gradient edges. The conclusion was not "the mapping
is wrong" — it was that *"equal to the black-box resampler's sample point" is the
wrong criterion*. The criterion is the documented convention, stated in the spec
and tested by golden vectors.

### Coverage — read this before citing

| Mode | Synthetic vectors | Real-device pixel verification |
|---|---|---|
| `stretch` | ✅ | ✅ **verified** (648,000 pixels exact) |
| `fit` | ✅ | ❌ **not verified** |
| `crop` | ✅ | ❌ **not verified** |

`fit` / `crop` are implemented and covered by synthetic vectors, but they have
**not** been verified pixel-by-pixel on a device. The AVD cannot produce a
letterboxed screenshot. Do not cite them as device-verified.

### API

```python
inv = InverseMap.from_screenshot(orig_w, orig_h, sent_w, sent_h, mode="stretch")
px, py = inv.to_device(mx, my)      # model point -> device pixel
```

Pure function, no I/O, no dependencies.

### Verify

```bash
cd screenpoint && python3 -m pytest tests/ -q
```

Or from the repository root: `./run-tests.sh`

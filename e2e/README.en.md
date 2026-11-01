# e2e · End-to-end integration demo

**[English](README.en.md)** · **[中文](README.md)**

**License** Apache-2.0

---

<a id="english"></a>

## English

### What it is

End-to-end demo: model point output → parse → inverse-map → real tap → verify.

Proves the coordinate chain works on a real device, not just in synthetic
vectors.

### The chain

```
model dirty text output
   →  pointparse   parse and validate, or report a distinguishable failure
   →  screenpoint  inverse-map to device pixels (deterministic code)
   →  adb          real tap
   →  screendiff   verify the screen changed as intended
```

Every arrow is a separate library. The demo exists to prove they compose — and
that the composition is what breaks, not the pieces.

### What is committed

Request/response samples under `data/e2e/`, in two layers:

| Layer | Contents | Used for |
|---|---|---|
| `fixtures/` | contract level: endpoints, status codes, field names, **field types** | 18 tests that **recompute offline, no AVD needed** |
| `raw/` | device level: full response bodies | diffing only, not asserted on |

The contract layer deliberately excludes `snapshot_id`, `bounds`, `cx`, `cy` and
byte counts — those change per device, and asserting on them produces false
failures on someone else's machine.

### Honesty note

The "external agent completes the full loop over public APIs" claim is a **proof
of concept run by this project itself**. The samples are real, the taps really
happened, and the reproducer was us. It is not an independent third-party
reproduction, and the top-level README says so.

### Verify

```bash
./run-tests.sh          # from the repository root; no device, no network
```

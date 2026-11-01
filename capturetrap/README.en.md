# capturetrap · Four silent traps in the capture layer

**[English](README.en.md)** · **[中文](README.md)**

**License** Apache-2.0 · **Version** 0.1.0 · **Date** 2026-10-27
**Test environment** AVD `avd-api35` (Android 15 / Google APIs / arm64-v8a)

---

<a id="english"></a>

## English

### What it is

Four silent traps in the `uiautomator dump` capture layer.

All four surface as "no data returned" rather than as errors, so they get
mistaken for a broken device.

### Why it exists

Every observation in this kit depends on one thing: the dump actually being
captured. When the capture silently fails, every downstream number is suspect —
and nothing says so.

Our own probe hit **three of the four** in a row, and all three presented as "no
data" rather than as errors.

### The four traps

| # | Trap | Symptom | Handling |
|---|---|---|---|
| 1 | Asynchronous flush | the file does not exist yet when the command returns | poll for `<hierarchy` |
| 2 | **OOM kill without `--compressed`** | output `Killed`, no file, **and a zero exit code** | try compressed first, fall back to plain |
| 3 | **The path is interpreted on the device** | a host path like `/var/folders/...` does not exist there | use `/data/local/tmp/...` |
| 4 | Overwriting in place | you read the previous capture | unique path per run |

**Trap 2 is the hardest to see**: it produces no file *and* no error, so the layer
above only experiences "polled N times and never saw XML". The first version of
`_adb_capture` hung exactly this way — the two earlier pytest runs were **60-second
timeouts, not failures**.

### A refuted claim, kept on purpose

An earlier observation concluded that `adb shell` converts LF to CRLF and pollutes
the XML. **Reproduction testing refuted it**:

```
adb shell     cat p.txt | xxd  →  610a 620a 630a   (pure LF)
adb exec-out  cat p.txt | xxd  →  610a 620a 630a   (identical)
newlines in the dump's XML      →  0
```

The two read methods are byte-identical, and the dump's XML is a single line with
zero newlines, so the trap cannot manifest here at all.

`exec-out` is still used — because it is *semantically* the raw byte stream, not
because pollution was observed. The spec records this as an **unreproduced**
claim, and `data/nav_experiments.json` keeps both the original observation and
the refutation.

### The pattern this library exists to name

> **A single observation plus a tidy pattern is high-risk.**

Four over-claims on the day this kit was built all had that shape. Three were
caught by human re-running; the fourth by a function. See `claimcheck` and
`docs/REFUTED.md`.

### Verify

```bash
cd capturetrap && python3 -m pytest tests/ -q
```

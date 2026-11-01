# uidref · Android UI element reference layer

**[English](README.en.md)** · **[中文](README.md)**

**License** Apache-2.0 · **Version** 0.1.0 · **Date** 2026-10-27
**Test environment** AVD `avd-api35` (Android 15 / Google APIs / arm64-v8a)

---

<a id="english"></a>

## English

### What it is

A reference layer for Android UI elements: let the model name an element
(`click e14`) instead of guessing pixel coordinates.

Flattening `uiautomator dump` XML loses most clickable targets, because they are
anonymous containers whose labels live in their children.

### Why it exists

`uiautomator dump` is the only observation channel available to a normal app
without root or ADB. Handed to a model raw, it is 276 KB of which **83.3% is
noise**: 789 nodes, of which only 132 (16.7%) are interactive.

The noise is not incidental — it is structural. The majority of interactive
nodes are anonymous `LinearLayout`s with no `text`, no `content-desc` and no
`resource-id`; their labels live in descendant `TextView`s. **Any noise reduction
that only keeps "elements with names" silently discards most of the tap
targets.** That is the central trap this library is built around.

### The core design decision

> A `ref` is a **document-order ordinal**, not an identifier. Ordinals carry no
> content, so a ref is only valid for the snapshot it was produced from.

`snapshot_id` is a content hash (`sha256(package|rotation|root_xml)[:12]`), so
"the index is in range" and "the meaning is still valid" have no connection. The
proposal in `提案/03-stale-ref/` closes that gap; see also
`docs/PORTABILITY.md` §10.

### Measured on a real device

| Metric | Value |
|---|---|
| Nodes → interactive | 789 → 132 (**16.7%**) |
| XML size → digest size | 276 KB → 8.6 KB (**32.3×**) |
| Interactive recall | **1.0** (independently recomputed, not reusing the implementation's own predicate) |
| Label coverage | 92.4% |
| Digest size per screen | ≤ 400 tokens |

The recall figure deserves a note: `test_actionable_count_matches_manual_count`
**does not reuse the implementation's own interactive predicate** — it recounts
from scratch and compares. Otherwise "recall 1.0" is self-certification.

### The digest format

One line per interactive element, in document order:

```
e3  btn     "Sound & vibration"        com.android.settings:id/row
e5  item    "Display"                  —
e9  input   "Search settings"          com.android.settings/search
```

Fields: `ref` · role (`btn`/`input`/`slider`/`switch`/`item`) · label · resource-id.
`disabled` is marked explicitly. The model answers with a ref, never a
coordinate.

### HTTP API

Zero dependencies, standard library only:

```
GET  /healthz
POST /snapshot    {"xml": "..."}  or  {"device": "emulator-5554"}
POST /resolve     {snapshot_id, ref}   -> {x, y, bounds, ...}
POST /tap         {snapshot_id, ref, device}
GET  /snapshots
```

**Security posture** (also stated in `审计表.md`):

- binds `127.0.0.1` by default; binding to another interface requires an explicit
  `--host` and prints a warning at startup
- **no authentication, no TLS**
- only `/tap` writes to the device; the rest are read-only

The design premise is "serves this machine only". Add your own authentication
before any cross-machine use.

### Known boundaries

1. `uiautomator dump` is asynchronous — the file may not exist yet when the
   command returns. Poll for `<hierarchy`.
2. The dump path is interpreted **on the device**, not on the host.
3. Binary files must not be read as UTF-8 (use `exec-out`).
4. refs are positional; see `提案/03-stale-ref/` for the invalidation gap.

### Verify

```bash
pip install -r ../../requirements.txt
cd uidref && python3 -m pytest tests/ -q
```

Or run the whole suite from the repository root: `./run-tests.sh`

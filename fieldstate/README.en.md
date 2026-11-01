# fieldstate · Can this input field be written to?

**[English](README.en.md)** · **[中文](README.md)**

**License** Apache-2.0 · **Version** 0.1.0 · **Date** 2026-10-27
**Test environment** AVD `avd-api35` (Android 15 / Google APIs / arm64-v8a)

---

<a id="english"></a>

## English

### What it is

Decide whether an input field can be written to: empty / focused / editable /
clearable.

`text == ""` is wrong — when a field is empty the dump reports the hint text
instead, so agents silently skip or clobber the field.

### Why it exists

Before you can write text (`textin`), you must know whether the field is writable
at all. Four predicates, all currently solved ad hoc by every agent:

| | Question | Common ad-hoc approach | This library |
|---|---|---|---|
| D1 | Is it empty? | `text == ""` | `!isShowingHintText()`; at the XML layer, **unknown** |
| D2 | Is it focused? | `focused` | `focused` (**not** `focusable`) |
| D3 | Is it editable? | class name contains `EditText` | `isEditable()`; class name is a heuristic |
| D4 | Is it clearable? | send 60 DEL keys | delete until the read-back stops changing |

### The core finding

The same field, the same node:

| Real field state | XML `text` | `isShowingHintText()` | `textSelectionStart` |
|---|---|---|---|
| **empty** (showing hint) | `"Search settings"` | **true** | **-1** |
| has content `PROBE` | `"PROBE"` | false | 5 |
| **empty** (no hint) | `""` | true | -1 |

`AccessibilityNodeInfo.getText()` is specified to **fall back to the hint** when
the text is empty — intentional, so TalkBack can announce it. But the XML dump
carries neither the hint itself nor `isShowingHintText()`.

Full inventory: the dump exposes 17 attributes and **never** exposes hint /
isShowingHintText / textSelectionStart / editable / cursorVisible / inputType.
**The XML is lossy, and exactly the fields needed for the predicates are the ones
it drops.**

Consequence: silent failure. The agent sees non-empty text → concludes "not
empty" → skips the write; or clears first, where the clearing is itself based on
`text != ""`. Neither path produces an error signal.

### Design principle

> **When you cannot tell, say you cannot tell.**

At the XML layer D1 returns `unknown` rather than guessing. A library that says
"I don't know" is more useful than one that gives a confident wrong answer — a
guess of "no keyboard" makes the agent tap air, a guess of "keyboard present"
rejects valid taps. Both are wrong.

### D4: clearing must not send empty text

`am broadcast --es text_b64 ""` makes **`am` itself throw**, the broadcast never
leaves, and the field keeps its content. `input text` likewise cannot carry an
empty argument. Clearing must therefore delete until the read-back stops
changing — not send an empty string.

### The `focus` field vs `is_focused`

They are **not equivalent** and the contract keeps both:

- `focus` — a stronger signal; `"none"` means no focused editable node was found
- `is_focused` — the raw boolean from the backend

The implementation must prefer the normalised `focused` and use the raw boolean
only as a fallback. A bug found by mutation scanning: when the backend reports
`focus: "none"` together with `is_focused: true` (dirty data or a stale
snapshot), the raw boolean used to override the normalised result and report
**"no focused editable node found" as focused**. Spec condition C8 now makes the
precedence a MUST, and the tests that were missing for that branch were added.

### Verify

```bash
cd fieldstate && python3 -m pytest tests/ -q
```

Real-device data is committed under `data/`.

# pointparse · Parsing and validating model point output

**[English](README.en.md)** · **[中文](README.md)**

**License** Apache-2.0 · **Version** 0.1.0 · **Date** 2026-10-27

---

<a id="english"></a>

## English

### What it is

Parse and validate point output produced by models; report failure instead of
guessing.

A confident-looking wrong coordinate is worse than an error, and every agent
re-implements this parsing ad hoc.

### Why it exists

"Click the search box" comes back from a model as text. Turning that text into a
coordinate is where GUI agents quietly break — not with an exception, but with a
plausible wrong answer.

The library's stance: **when the output cannot be uniquely resolved to one point,
report the ambiguity.** Never average, never pick the first, never round
hopefully.

### 38 cases of real dirty output

The vectors are not synthetic edge cases; they are the shapes models actually
emit. Among them:

**The thousand-separator ambiguity**

```
"1,400, 900"   → naive regex parses (1, 400)
```

`1,400` looks like a number with a thousands separator; `900` is the second
coordinate. The naive parse yields `(1, 400)` — a completely ordinary-looking
wrong point. This is the single most dangerous case in the set, because nothing
about the result looks broken.

### Design rules

- **No point found is a normal, reportable outcome** — the model saying "I can't
  see the target" is legitimate output, and must be reported as a distinguishable
  failure type, not swallowed
- **Ambiguity must be reported**, not resolved by preference
- **Only clues are returned** — never probabilities or confidence scores, which
  invite the caller to make the decision the parser should have made
- **The caller must combine clues with its own declared space**; the parser must
  not silently decide the scaling

### Failure types

```
NoPointFound     the model explicitly could not locate the target
Ambiguity        the output resolves to more than one point
Malformed        the output does not parse at all
```

### Cross-language implementation

A second, independently written implementation exists in `js/impl.js` (not a
translation — a separate implementation, which is what makes the spec's clarity
testable). Golden vectors run green in both languages; see
`uidref/docs/PORTABILITY.md` for the methodology.

### Verify

```bash
cd pointparse && python3 -m pytest tests/ -q
```

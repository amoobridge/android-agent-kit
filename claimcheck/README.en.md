# claimcheck · Verification levels for empirical claims

**[English](README.en.md)** · **[中文](README.md)**

**License** Apache-2.0 · **Version** 0.1.0 · **Date** 2026-10-27

---

<a id="english"></a>

## English

### What it is

Verification levels for empirical claims: hypothesis, reproducible, cross-state,
cross-validated, refuted.

A single observation plus a tidy pattern is the most dangerous thing in this
project.

### Why it exists

On the day this kit was built, five statements that looked like discoveries turned
out to be false. They shared one shape: **a single observation, plus a tidy
pattern, plus confidence.** Every one of them would have been written into
documentation as a conclusion.

`claimcheck` is the executable form of the lesson: grade every empirical claim,
and refuse to let anything below a threshold be cited.

### The levels

| Level | Meaning | Citable |
|---|---|---|
| **V0** | hypothesis — a single observation, or an unexcluded alternative explanation | ❌ |
| **V1** | reproducible — repeated, or deterministic from committed inputs | ✅ |
| **V2** | cross-state — reproduced across different starting states | ✅ |
| **V3** | cross-validated — reproduced through independent channels | ✅ |
| **V4** | refuted — a conclusion once held, now overturned | ❌ (archived) |

`MIN_LEVEL_FOR_SPEC = V1`: below V1, nothing may be written into a specification.

### Two rules that look small and are not

**① Three parameters are counted separately.** Reproducing 10 times from the same
starting state is still V1, not V2. Cross-*state* means the starting state
actually varied.

**② A single observation alone is enough to trigger verification.** The first
version of `should_verify_before_writing` required ≥ 2 danger signals, which let
the `am start` claim — the one with a control group and a single observation —
**escape**. It was the most discovery-like statement of the day. The rule is now:
one observation is sufficient, no signal-counting required.

### Refuted ≠ deleted

`refute()` moves a claim to V4, records `refuted_by`, and **keeps the original
observation**. Deleting it means nobody knows a conclusion ever stood here, and
the next person rediscovers it from scratch.

The `original_observation` + `refuted_by` pair is itself teaching material — the
mechanism of one of today's misattributions only became clear *after* it was
archived.

`citable` returns False for V4 **even with 10 observations behind it**.

### `deterministic`: the field that was missing

`classify()` originally assumed "observations = repeated sampling". But a large
share of this project's claims are **deterministic computations over committed
inputs** — running once *is* one observation, and the honest grade is not raised
by inflating a counter. The `deterministic` field is what legitimately promotes
such a claim to V1.

### Verify

```bash
cd claimcheck && python3 -m pytest tests/ -q
```

`TestTodaysRealCases` pins the five real over-claims from that day as fixtures:
all are caught, all are V4, none is citable, all retain their original
observation.

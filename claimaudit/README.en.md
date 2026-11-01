# claimaudit · Running claimcheck across every asset

**[English](README.en.md)** · **[中文](README.md)**

**License** Apache-2.0 · **Version** 0.1.0 · **Date** 2026-10-27

---

<a id="english"></a>

## English

### What it is

Apply `claimcheck` to every quantitative claim across the asset set, and
recompute the levels.

Writing the ledger itself triggers over-claiming, because summarising your own
evidence carries an optimism bias.

### Why it exists

`claimcheck` defines the rules. This library **runs them** — and immediately
caught that 11 of 16 claims had been written one level too high.

| Claim | As written | Recomputed |
|---|---|---|
| uidref compression 32.3× | V3 | **V0** (obs = 1) |
| crosstrack false_match 100% | V1 | **V0** (obs = 1) |
| imespec 5/13 unreachable | V1 | **V0** (obs = 1) |

**Root cause**: `classify()` assumed "observations = repeated sampling", while
most of this project's claims are **deterministic computations over committed
inputs**. Running once *is* one observation. The fix is the `deterministic` field
— **not** inflating an observation count.

### The correction ran in both directions

The same recompute also caught the opposite error: `capturetrap-stale` was marked
V0 by hand, while `classify()` recomputed it as **V1** from 5 observations. But it
has an unexcluded alternative explanation ("the screen genuinely did not change")
and was explicitly demoted back to V0.

> **A claim can be observed many times and still not be citable.**

### The most important finding about this tool

> **The act of writing the ledger is itself what triggers over-claiming.**

Every time the ledger was expanded, the recompute caught new errors — the same
day the rules were written down, one of them was broken again while writing a
proposal. The bias is not a one-off mistake; it is structural.

So `claimaudit` is not a one-time cleanup. It is a gate that must be re-run
whenever the ledger grows.

### Usage

```bash
python claimaudit/tools/audit_claims.py            # human-readable summary
python claimaudit/tools/audit_claims.py --json     # machine-readable, for archiving
```

The tool prints the recomputed level next to the recorded one and exits non-zero
on any mismatch.

### Verify

```bash
cd claimaudit && python3 -m pytest tests/ -q
```

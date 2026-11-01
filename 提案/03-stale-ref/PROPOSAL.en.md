# Proposal 03 · uidref reference invalidation: from "reference gone" to "reference reassigned"

**Target**: the `uidref` specification
**License**: Apache-2.0 · **Date**: 2026-10-27 · **Status**: proposal
**Evidence**: 4 real device dumps + AVD closed-loop run + regression tests

---

## 1. In one sentence

`uidref`'s `StaleRefError` only covers one kind of invalidation — *the reference
is gone*. On a real device there is a second kind, and it is the more dangerous
one: **the reference still resolves, but now points at something else.** This
proposal upgrades the failure criterion from "is the index in range" to "is this
still the same snapshot".

---

## 2. The problem, found on a real device

In the `agentloop` controlled experiment S3 (policy sees the screen one beat
late), the expectation was:

> The reference-based policy would reject stale references at parse time with
> **0 missed taps**; the coordinate-based policy would tap regardless and
> produce misses.

Measured: **both tapped exactly once, and the reference-based one tapped the
wrong thing.**

On that frame, the index `e5` was **still valid** — but it had changed from
"Security & privacy" to "Connected devices · Bluetooth". `resolve("e5")`
returned a perfectly normal `Element`; the tap landed silently on the wrong row
and navigated to the wrong page.

```
reference gone         → StaleRefError → execution rejected      ✅ covered
reference reassigned   → resolve() OK  → wrong tap               ❌ not covered
```

**Why the second kind is worse**: it produces no error signal at all. A missed
tap is at least detectable by `screendiff` as `target_unchanged`; a *wrong* tap
navigates somewhere else, and all the agent ever sees is a "successful tap".

---

## 3. Root cause: refs are ordinals, not identifiers

A `uidref` `ref` is a **document-order index** (`e1`, `e2`, …). Ordinals have
two properties:

| Property | Consequence |
|---|---|
| Carries no content information | The same index points at different elements under different content |
| Shifts wholesale when content changes | Insert one row at the top and everything below is off by one |

`snapshot_id`, meanwhile, is a **content hash**
(`sha256(package\|rotation\|root_xml)[:12]`). So "the index is in range" and
"the meaning is still valid" have **no connection whatsoever** — that is the gap.

---

## 4. Evidence from real dumps

Ref-by-ref comparison over the real dumps in `screendiff/dumps/` (not
constructed data; 11 interactive elements per snapshot, **counted exhaustively,
not sampled**):

| Transition | same snapshot_id | reassigned refs | note |
|---|---|---|---|
| `c1 → c2` | no | **11 / 11 (100%)** | cross-page navigation |
| `c1 → c3` | no | **11 / 11 (100%)** | cross-page navigation |
| `c1 → d1` | no | **11 / 11 (100%)** | cross-page navigation |
| `c2 → c3` | no | 1 / 11 | same-page label change (airplane-mode switch) |
| `c2 → d1` | no | 1 / 11 | same-page label change |
| `c3 → d1` | no | **0 / 11** | pure scroll; 9 elements moved but every label identical |

Four readings, each making one point:

1. **Cross-page navigation is 100% reassignment.** After one page hop, *every*
   ref from the previous page points at different content. This is not an edge
   case; it is the normal state after navigating.
2. **Same-page content change also reassigns** (1/11) — even when the screen
   still looks like "the same page".
3. **Pure scroll does not reassign** (0/11): 9 elements moved, not one label
   changed.
4. **But the snapshot_id changed on every transition.**

Points 3 and 4 together form the key design constraint; see §5.3 and §6.

> Worth recording: the first version only counted `e1..e6` and concluded
> "6/6", underestimating by nearly half. *The coverage of a statistic needs its
> own criterion too* — that is this proposal's own lesson.

---

## 5. The proposal: two-gate resolution

### 5.1 API change

```python
# current (v0.1)
snap.resolve("e5") -> Element
    # raises StaleRefError only when the index is out of range

# proposed (v0.2)
snap.resolve(ref, since=None) -> Element
    # gate 1: index out of range      → StaleRefError(reason="ref_gone")
    # gate 2: since != own id         → StaleRefError(reason="snapshot_mismatch")
```

`Decision` gains a required field `since`, **carried by the policy when it
emits the decision**:

```python
@dataclass
class Decision:
    kind: str                       # tap_ref | tap_xy | swipe | done | fail
    ref: str | None = None
    since: str | None = None        # id of the snapshot this ref came from; required for tap_ref
    ...
```

The executor cannot forget to check, because `since` lives in the decision
object — without it, a `tap_ref` is not a well-formed decision at all.

### 5.2 Why it will not over-reject

`snapshot_id` is a content hash ⇒ **content unchanged means id unchanged, and
the reference stays valid.**

```
screen unchanged → same id → resolve(ref, since=id) succeeds   no re-dump needed
screen changed   → different id → must re-observe
```

That is exactly the desired behaviour: **do not disturb when nothing changed,
force re-observation the moment something does.**

### 5.3 The cost, and why it is acceptable

Pure scrolling (`c3 → d1`) changes the id, so all refs are invalidated and a
re-dump is required. In other words: **after every scroll, every reference is
void.**

Acceptable, for three reasons:

1. **A correct agent loop re-observes after every action anyway** — otherwise it
   cannot tell whether the action had any effect. `screendiff` exists precisely
   for this. Re-dumping is not overhead; it is a required step of the loop.
2. Scrolling *is* an action, and must be verified to have scrolled to the right
   place.
3. Trading "the cost of a re-dump" for "not tapping the wrong thing" is a good
   deal in any agent scenario — one wrong tap derails the whole task chain,
   while one dump costs a few hundred milliseconds.

If cross-scroll element tracking is genuinely needed, that is a **separate
requirement**; see §7.

---

## 6. The deeper distinction: refs express identity, labels express description

On the surface S3 was a missing invalidation check. In substance, **two
different intents were conflated**:

| Intent | Correct tool | Semantics |
|---|---|---|
| "the row I saw" | `resolve(ref, since)` | **identity** preserved; invalid as soon as the screen changes |
| "the row currently labelled X" | `find_by_label(snap, label)` | **description** matched; always based on the latest observation |

In S3 the policy wanted the latter ("the Security & privacy row") but used the
former. With the two gates in place, that misuse **fails loudly** instead of
silently tapping the wrong row — which is more valuable than having it happen
to work.

**The specification should state explicitly** that `resolve` and
`find_by_label` are not interchangeable, and that a `tap_ref` may only be
produced by `resolve`, never by passing off a `find_by_label` result as a ref.

---

## 7. Out of scope: stable element keys

"All refs die after a scroll" is a real cost for some agents. The thorough fix
is a **content-derived stable key** per element (for example
`resource-id + class + label + ordinal among same-named siblings`), so the same
row keeps the same key across scrolls.

That requires solving three problems independently: the collision-resolution
rule, the degradation behaviour when a key is missing, and the matching
algorithm between pre- and post-scroll keys (highly homologous to `screendiff`'s
matching problem).

**Recommended as a separate effort**, not folded into this revision. This
proposal only does invalidation detection, to establish safety first.

---

## 8. Specification clauses (to be written into uidref SPEC §8)

| # | Level | Clause |
|---|---|---|
| R1 | MUST | `resolve(ref, since)` raises `StaleRefError` with `reason="snapshot_mismatch"` when `since` differs from the current `snapshot_id` |
| R2 | MUST | `StaleRefError` carries a `reason`, either `ref_gone` or `snapshot_mismatch` |
| R3 | MUST | when `Decision.kind == "tap_ref"`, `since` is required; a missing value makes the decision invalid |
| R4 | MUST | resolution failure must not fall back to "the nearest live element" or any silent correction |
| R5 | MUST | an implementation must not use a `find_by_label` result as the ref for a `tap_ref` |
| R6 | SHOULD | `snapshot_id` derives from the full content (hash), so an unchanged screen produces the same id |
| R7 | MAY | provide stable element keys for cross-snapshot tracking; if provided, collision resolution and matching rules must be specified separately |

**Keywords** (RFC 2119): MUST / MUST NOT / SHOULD / MAY.

---

## 9. Verification

See `tests/test_stale_ref.py`: **18 tests**, all based on the real dumps in
`screendiff/dumps/`.

| Assertion | Criterion |
|---|---|
| Cross-page reassignment is rejected | `c1`'s `e5` resolved against `c2`/`c3`/`d1` → `snapshot_mismatch` |
| Cross-page is 100% reassignment | all three cross-page transitions are 11/11 (`test_cross_screen_reassigns_everything`) |
| Same-page label change is rejected | `c2`'s `e3` resolved against `c3` → `snapshot_mismatch` |
| Same snapshot is not over-rejected | `since` equal to own id → resolution succeeds |
| Unchanged screen is not over-rejected | parsing the same XML twice → same id → succeeds |
| Out-of-range still reports `ref_gone` | `e999` → `ref_gone` |
| Pure scroll is also rejected | `c3 → d1` has 0 reassignments but a different id → still rejected (**safety first**) |
| The two reasons are distinguishable | the caller can decide "re-dump" vs "re-search" |
| **Old behaviour would have passed silently** | `test_old_behaviour_would_have_succeeded` proves the gap is real |

The last row is the reason this proposal exists: it asserts that *the same
input, without `since`, does not raise*. If it ever fails, uidref has been
fixed and this proposal can be closed.

---

## 10. Scope

Applicable because:

- the problem is real (reproduced on device + quantified over 4 real dumps)
- the fix is minimal (one parameter + one required field) and breaks no existing API semantics
- it has regression tests, and those tests use real dumps rather than constructed data
- naming discipline: no third-party application is named anywhere; only elements, snapshots and references are discussed
- technically harmless: pure client-side logic — no permissions, no network, no system calls

**Recommended to be submitted together with the uidref main body**, as a
revision to SPEC §8 and `resolve()`.

---

## Verification level

Quantitative claims in this proposal are registered in **`docs/CLAIMS.md`**
(`claimaudit/data/evidence_ledger.json`).

Recompute with: `python claimaudit/tools/audit_claims.py`

**Levels claimed here**:

| Claim | Level | Citable |
|---|---|---|
| Cross-page navigation reassigns 100% (11/11 × 3) | V1 | ✅ |
| Same-page content change also reassigns (1/11) | V1 | ✅ |
| Pure scroll does not reassign (0/11) | V1 | ✅ |
| snapshot_id changed on every transition | V1 | ✅ |
| First version counted only e1..e6 and got 6/6 (self-correction) | V1 | ✅ |

All inputs above are the already-committed real dumps in `screendiff/dumps/` —
**anyone can recompute them.**

**Rule** (from `claimcheck`): a single observation may only produce a hypothesis,
never a conclusion; nothing below V1 may be cited as a conclusion; anything
refuted (V4) must be archived and marked "not to be cited as a conclusion".

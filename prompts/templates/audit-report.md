# Tech Debt Audit — jarvis — <YYYY-MM-DD>

<!--
Template for the read-only audit genre. Written to
`prompts/tasks/<N>-<slug>.md` so the report becomes the next numbered task
spec, ready to be remediated. No source file is modified during an audit.
-->

## Summary

One paragraph on the overall health of the codebase — size (source vs test
LOC), what's genuinely good, and what kind of debt dominates.

**Findings by severity:** High: <n> · Medium: <n> · Low: <n> (<total> total)

**Top 5, in priority order:**
1. **[H1]** <one-line statement of the issue and its consequence>
2. **[H2]** <…>
3. **[M1]** <…>
4. **[M2]** <…>
5. **[M3]** <…>

---

## Findings

<!-- Grouped by severity: all High first, then Medium, then Low. -->

### [HIGH] <Short title>
- **Location:** `path/to/file.py:12-30`; `other/file.py:4`
- **Category:** structure | tech-debt | anti-pattern | test-gap
- **Description:** What's wrong, in plain language. Reference the actual code,
  not a guess about it.
- **Why it matters:** Concrete consequence — bug risk, onboarding cost,
  performance, security. Not "it's bad practice".
- **Suggested fix:** Brief and directional; not a full implementation.
- **Effort estimate:** S / M / L

### [MEDIUM] <Short title>
- **Location:**
- **Category:**
- **Description:**
- **Why it matters:**
- **Suggested fix:**
- **Effort estimate:**

### [LOW] <Short title>
- **Location:**
- **Category:**
- **Description:**
- **Why it matters:**
- **Suggested fix:**
- **Effort estimate:**

---

## Test coverage summary

| Module / area | Coverage | Notes |
|---|---|---|
| `<module>/` | Strong / Good / Weak / None | <what's covered, what gap matters> |

**Pattern-level notes:**
- Test-quality observations across the suite (over-mocking, happy-path only,
  missing error injection) — not file-by-file unless notable.
- If no coverage tool is configured, say so: these are qualitative
  assessments, not measured percentages.

---

## Open questions

1. <Anything ambiguous, skipped, or needing owner input before remediation.>

---

<!--
Severity definitions:
- High   — actively causing or likely to cause bugs / security exposure, or
           actively blocking changes.
- Medium — not urgent but compounding; more expensive the longer it's left.
- Low    — cosmetic or minor inconsistency, fine to defer indefinitely.

Effort: S = under a day · M = a few days · L = needs planning/design.
-->

# Coherence checkpoints

Slice-boundary audits by the `auditor` role (Opus, read-only), run when a
vertical slice or epic closes and before any architecturally load-bearing
issue. Per-PR review covers diff-level correctness; these cover what a diff
cannot see: cross-issue coherence, concept duplication, cross-layer contract
rot, spec divergence, and emergent boundary gaps.

One file per run: `<YYYY-MM-DD>-<slice-name>.md`. Each run diffs against the
previous checkpoint, so coherence is tracked as a trend. Verdict is `COHERENT`
(next slice may proceed) or `NEEDS-WORK` (named items gate the next slice).

Brief: `.claude/briefs/auditor.md`. Loop: `docs/sdlc.md` (Worker harness).

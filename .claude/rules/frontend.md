---
paths:
  - "frontend/**"
---

# React / Next.js idiom — default posture

Idiomatic by default. A deviation needs a `decisions.md` entry (what, why,
revisit trigger) in the same PR — no human sign-off. Non-idiomatic code
without a logged decision is a review finding.

## React

- Function components + hooks only. Hooks called unconditionally at top
  level; effect dependency arrays complete — a lint suppression is a
  deviation and needs its decision entry.
- Props fully typed; no `any` on component boundaries. Variants via `cva`,
  class merging via `cn()` (the sole `lib/utils.ts` export).
- No business logic inside components: it lives in stores and hooks;
  components render state and dispatch intents.

## State management

- Server state lives in TanStack Query (caching, retries, invalidation) —
  never mirrored into zustand. Client/UI state lives in zustand stores
  (`stores/`, per the repo layout). Derived values are selectors, not
  stored copies; one authoritative home per fact.
- SSE: exactly one connection owner (a hook); events are dispatched using
  the vocabulary mirrored in `lib/sse.ts`; components subscribe to store
  slices and never parse raw event payloads.

## State machines

- Multi-phase UI status (agent panel: idle / streaming / tool-running /
  capped / replay) is one discriminated union driving rendering — not
  accumulating booleans. Transitions are functions; impossible combinations
  don't typecheck.

## Next.js (D13 constraints)

- Static export: no dynamic route segments, no server actions; URL state
  via search params (`?paper=`). API access only through `lib/api-client.ts`
  with types from `lib/api-types.gen.ts` (generated, never hand-edited).

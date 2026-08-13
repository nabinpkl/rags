---
paths:
  - "frontend/**"
---

# React / Next.js idiom — askRAG residue

The binding idioms now live in the taste plugin: **taste:web-stack** owns the
React deltas (function components + hooks, complete dep arrays, `cva`/`cn`, dumb
components), the data-ownership split (server state in TanStack Query, client
state in zustand, never mirrored; one home per fact), state machines over boolean
soup, and the **set-once/churn-field** rule (a value set once and read elsewhere
gets its own field, never folded into a churny status union — the live/replay
session-mode bug, `DECISIONS.md` 2026-07-09). Idiomatic by default; a deviation
needs a `DECISIONS.md` entry in the same PR — no human sign-off. Undocumented
non-idiom is a review finding.

Only askRAG-specific facts live here:

- **Gate**: `just check` (or the frontend half when only frontend changed).
- `cn()` is the sole export of `lib/utils.ts` (the one grab-bag exception).
- **SSE / API surface**: events dispatched using the vocabulary mirrored in
  `lib/sse.ts`; API access only through `lib/api-client.ts` with types from
  `lib/api-types.gen.ts` (generated, never hand-edited).
- **Interactive affordances are base-layer, hover colour is per-component**
  (#87): cursor and the focus ring live once in `app/globals.css` so they hold
  for controls that don't exist yet — never re-spell them on a component.
  Hover *colour* is per-component (it depends on the surface), and it goes in
  the shared part of a `cn()`, never in the unselected branch of a
  conditional: a selected control that stops reacting to the pointer reads as
  disabled. Palette tokens for hover states are in `globals.css` alongside the
  colours they step from.
- **Next.js is static-export here (D13), and this diverges deliberately from
  sibling repos** (chatbot is SSR/RSC): `output: 'export'`, no server actions, no
  dynamic route segments; URL state via search params (`?paper=`). This section is
  NOT shared — it is downstream of askRAG's public, budget-capped, flat-cost-VPS
  hosting, not a general default.

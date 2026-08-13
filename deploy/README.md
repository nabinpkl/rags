# Deploying askRAG

Two containers behind one origin (D13): `api` (FastAPI + the agent loop) and
`web` (the Next.js static export served by Caddy, which also proxies `/api`).
The sandbox (D10) is not a service — it is spawned per execution.

Ingress binds **loopback only**. How that port reaches people is the one thing
that differs between deployments:

| Mode | Ingress | Status |
|---|---|---|
| Tailnet | host `tailscaled` fronts `127.0.0.1:8420` via `tailscale serve` | shipped (#81) |
| Public | Caddy site block + auto-TLS + Cloudflare | #37 |

## First deploy

```bash
cp deploy/.env.example deploy/.env   # then fill it in — the salt is required
just deploy                          # build images, seed chroma, start
just deploy-tailnet                  # publish onto the tailnet
```

`deploy/.env` must carry a real `ASKRAG_TRACE_IP_HASH_SALT` (`openssl rand -hex
32`) — compose refuses to start without one, because an unsalted IP hash is a
rainbow-table lookup away from being an IP again (§6).

`just deploy-tailnet` needs the tailscale operator; grant it once with

```bash
sudo tailscale set --operator=$USER
```

or run the `tailscale serve` line it prints under `sudo`.

## What is mounted, and what is deliberately not

- `corpus.db` and `models/` — **read-only**. `corpus.db` is opened `mode=ro` by
  construction (D4).
- `chroma/` — copied into a container-private volume on first deploy, because
  Chroma writes to its own SQLite on open. The host snapshot is never opened
  writable (DECISIONS.md 2026-08-11).
- `traces.db` — a named volume, the one writable store (D13).
- `pdfs/` — **not mounted into anything**, and `corpus/` is excluded from every
  build context. §6b holds because the bytes are absent, not because a route
  declines to serve them.

## Everyday commands

```bash
just deploy-logs        # follow both containers
just deploy-down        # stop; volumes (traces, chroma) survive
just deploy-tailnet-off # withdraw the tailnet listener, keep serving on loopback
just deploy-reseed      # rebuild the chroma volume after a re-ingest (D12 refresh)
```

## Disk

`just deploy` rebuilds through BuildKit, whose cache mounts (uv's wheel cache,
pnpm's store) grow by gigabytes across repeated rebuilds — ~17 GB after a
day of iterating, on a box that also holds a 12 GB corpus. When the disk gets
tight:

```bash
docker builder prune -f && docker image prune -f
```

Neither touches the running containers or the tagged images they use; the next
build is just slower.

## Refreshing the corpus (D12)

Ingest locally, copy the new `corpus.db` / `chroma/` into place on the host, then
`just deploy-reseed`. Prod never runs the ingest chain.

## Agent provider

Prod (D3) is Claude Haiku: leave `ASKRAG_AGENT_API_BASE_URL` empty and set
`ANTHROPIC_API_KEY`. The tailnet box runs the cheap-first seam instead
(OpenRouter + `ASKRAG_SMOKE_MODEL`), so a private demo costs cents. Budget caps
(D11) are enforced server-side either way.

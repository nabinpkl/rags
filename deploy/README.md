# Deploying askRAG

Two containers behind one origin (D13): `api` (FastAPI + the agent loop) and
`web` (the Next.js static export served by Caddy, which also proxies `/api`).
The sandbox (D10) is not a service — it is spawned per execution.

Ingress binds **loopback only**. How that port reaches people is the one thing
that differs between deployments:

| Mode | Ingress | Status |
|---|---|---|
| Tailnet | host `tailscaled` fronts `127.0.0.1:8420` via `tailscale serve` | shipped (#81) |
| Public | `tunnel` container dials out to Cloudflare, which serves `rag.nabin.org` | see Public site below |

## First deploy

```bash
cp deploy/.env.example deploy/.env   # then fill it in — the salt is required
just deploy                          # build images, seed chroma, start
just deploy-tailnet                  # publish onto the tailnet
```

For the public site, also put the tunnel token in `deploy/.env`
(`CLOUDFLARE_TUNNEL_TOKEN`) before `just deploy`; see "Public site" below.

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
just deploy-public-off  # stop the tunnel; blank the token too or the next deploy restarts it
just deploy-reseed      # rebuild the chroma volume after a re-ingest (D12 refresh)
```

## Public site (Cloudflare tunnel)

`rag.nabin.org` reaches the stack through a remotely-managed Cloudflare
tunnel, the same shape as the other services on this host: the `tunnel`
container dials out to Cloudflare, so the box opens no inbound port and holds
no certificate, and Cloudflare terminates TLS. Its one route,
`rag.nabin.org -> http://web:8080`, lives in the Cloudflare dashboard;
the token in `deploy/.env` is all the box knows. With a token set, `just
deploy` starts the tunnel along with everything else (compose profile
`public`); without one the stack is tailnet-only.

The visitor's address survives the hop: Cloudflare appends the address it
saw to `X-Forwarded-For`, Caddy trusts the compose subnet the tunnel sits on,
and the API takes the rightmost address it does not trust
(`askrag/api/client_ip.py`), so a pre-seeded header cannot pick someone
else's budget.

Zone settings the site depends on, scoped to the `rag.nabin.org` hostname
(Configuration Rules, not zone-wide toggles, so the zone's other hosts keep
theirs):

| Setting | Value | Why |
|---|---|---|
| Rocket Loader, Email Obfuscation, Web Analytics auto-inject | off | each injects a script the CSP blocks |
| Cache Rule: GET `/api/*` | eligible for cache, respect origin TTL | Cloudflare skips extensionless JSON by default; the API's `Cache-Control` does nothing without this |
| Rate limit (free plan's one rule) | `/thumbs/*` while the agent is off, `/api/chat` once it is on | an uncached thumbnail renders a PDF on the box; a chat turn spends money |
| Always Use HTTPS | on | |
| HSTS | on after a clean week | hard to undo |

Cloudflare caches `/api` reads for up to an hour (`api_cache_control`), so
after a corpus redeploy purge the hostname's cache or the site shows the old
snapshot until it expires.

Resources (account and zone `nabin.org`; no secrets here):

| Resource | Id |
|---|---|
| Tunnel `askrag` | _added when created_ |
| DNS `rag.nabin.org` (CNAME to the tunnel, proxied) | _added when created_ |

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

The corpus itself does not need to live inside the checkout. Point
`ASKRAG_CORPUS_HOST_DIR` in `deploy/.env` at wherever the snapshot is (a
dedicated data volume, say) and leave `corpus/` as a symlink to the same place
so the collector and the ingest recipes, which resolve paths relative to the
repo, keep working. Compose bind-mounts the real path; it never reads the
symlink.

## Host reboots

The host runs `netfilter-persistent`, which replays `/etc/iptables/rules.v4` at
boot. That file is a snapshot of whatever Docker, k3s and tailscaled had written
at the moment someone last ran `netfilter-persistent save` — including Docker's
per-container `raw PREROUTING … ! -i br-<id> -j DROP` rules. Docker never
removes rules it did not write, so a rule saved for a network that has since
been deleted comes back every boot and drops traffic to whichever containers
now hold those addresses. On 2026-08-15 this silently cut `web -> api` for eight
days while both containers reported healthy (the API's own probe runs over
loopback inside the container).

Two things in `compose.yml` make this deployment immune regardless of what the
host or other projects do: the network has its own subnet (`10.120.0.0/24`,
nobody else's range) and a fixed bridge name (`askrag0`, so a stale snapshot of
*our own* rules is identical to what Docker writes anyway). The `web`
healthcheck goes through the proxy to the API, so a broken path shows up in
`docker compose ps`.

If it ever happens anyway, the tell is `DOCKER-*` chain counters at zero while
one rule in `sudo iptables -t raw -S PREROUTING` names a bridge that is not in
`/sys/class/net/`. Delete it and purge its lines from `rules.v4`.

## Refreshing the corpus (D12, as amended)

Prod never runs the ingest chain. Run it where the corpus lives, in this order —
each stage reads the previous one's output, and `build_indexes` is
drop-and-rebuild so it must be last:

```
just citations   # extract the citation graph, resolve what it points at
just frontier    # derive the index manifest, fetch + extract its papers
just index       # chunk, embed, rebuild corpus.db + chroma, then VERIFY
```

`just index` ends with `select_frontier --verify`, which fails if any paper the
landing page names lacks chunks. That check is the deploy gate: a green verify
means every link on the page opens; a red one means visitors would hit dead
ends, so do not ship the snapshot.

Then copy the new `corpus.db` / `chroma/` into place on the host and
`just deploy-reseed`.

## Agent provider

Prod (D3) is Claude Haiku: leave `ASKRAG_AGENT_API_BASE_URL` empty and set
`ANTHROPIC_API_KEY`. The tailnet box runs the cheap-first seam instead
(OpenRouter + `ASKRAG_SMOKE_MODEL`), so a private demo costs cents. Budget caps
(D11) are enforced server-side either way.

---
tags: [gotcha, deployment, networking, security]
date: 2026-09-07
---

# Gotcha - A LAN Server Bound to the Network and Refused It

## What happened

Server 3 (`192.168.200.129`) was configured to serve the office LAN. Its console said

```
Uvicorn running on http://0.0.0.0:8080
Serving all interfaces
```

and the desktop client could not reach it, so it stayed on the Render fallback. Roughly forty
minutes went into the network layer: firewall rules, `Test-NetConnection`, raw `TcpClient`
probes. All of it was the wrong layer. The answer was one line already in the server's own log:

```
[WARNING] Rejected request with unauthorized Host header: 192.168.200.129:8080
```

`verify_host` in `main.py` matches the Host header against `ALLOWED_HOST_NAMES`, which is
`{localhost, 127.0.0.1, ::1}` plus whatever `ALLOWED_HOSTS` adds. `ALLOWED_HOSTS` was empty, so
the server accepted the TCP connection, read the request, and refused it — with a message that
says `localhost`, on a server deliberately not bound to localhost.

## Why it cost so long

Two measurements disagreed and the disagreement was not investigated. `Test-NetConnection` said
the port was open once; `curl` reported connection refused; later probes said closed three times
running. That looked like a flaky firewall and was actually a restart: `curl` beat startup by
sixteen seconds, twice, and succeeded on the third try. A measurement taken across a restart is
not a measurement.

The 403 body compounded it. "Standalone backend only accepts localhost requests" describes the
default configuration rather than the request that was refused, so it reads as a build that was
never meant to serve a LAN — which is the one conclusion that stops you looking at `.env`.

## The rule

Serving a LAN is two settings in two layers, and configuring one is silent:

| Set only | Symptom |
| :--- | :--- |
| `SIDECAR_HOST=0.0.0.0` | Listens on the LAN, 403s all of it |
| `ALLOWED_HOSTS=<ip>` | Never listens on the LAN at all |
| Neither `API_TOKEN` | `/health` passes, every authenticated request 401s |

The third row is the one waiting behind the first two. With no `API_TOKEN`,
`initialize_local_api_token` generates one and writes it to the server's own disk. A remote client
has no way to read that file, so it authenticates against a secret it cannot obtain while
`/health`, which needs no token, keeps the banner green. Same shape as
[[Gotcha - The Installed App Bound to a Storage Directory at the Drive Root]].

And the client holds ONE remote token for both the primary and the fallback
(`connectionStore.ts` uses `remoteApiToken` for each), so a LAN server whose `API_TOKEN` differs
from Render's cannot work — whichever one you set it to, the other 401s.

## What was changed

- `.env.template` carries a commented LAN block naming all three variables together, because the
  person deploying reads the template and not `main.py`.
- `tests/test_lan_deployment_layers.py` pins the guard's LAN behaviour and fails if the template
  ever offers `SIDECAR_HOST=0.0.0.0` without `ALLOWED_HOSTS` and `API_TOKEN` beside it.

## Related

- [[ADR-013 Cloud Deployment Topology with Gated CI-CD]] — the three topologies
- [[Gotcha - The Installed App Bound to a Storage Directory at the Drive Root]] — the other
  green-banner-and-401 failure

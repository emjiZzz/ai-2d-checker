---
tags: [gotcha, database, deployment, networking]
date: 2026-09-08
---

# Gotcha - A Dead Atlas Socket Wedged Every Request

## What happened

Server 3 stopped answering. Not refusing — answering. The distinction is the whole diagnosis:

```
Test-NetConnection 192.168.200.129:8080 -> TcpTestSucceeded : True
curl http://192.168.200.129:8080/health  -> 000 after 20s
```

HTTP `000` means no response was received at all. The kernel completed the handshake because the
listener socket was alive; no handler ever wrote a reply. It never recovered on its own, and a
second workstation could not connect either, which is what ruled out anything client-side.

`Get-NetTCPConnection -LocalPort 8080` named the cause:

| State | Count |
| :--- | :--- |
| CLOSE_WAIT | 18 |
| Listen | 1 |
| ESTABLISHED | **0** |

CLOSE_WAIT means the peer sent FIN and the local application never called `close()`. Eighteen of
them with zero ESTABLISHED says every client had given up while every handler was still stuck
inside its request. The server was not idle and not crashed. It was blocked.

## Why

`connection.py` built the Motor client with `serverSelectionTimeoutMS=4000` and nothing else.

That bounds *finding* a server. It does not bound a read on a socket that has already been
selected, and PyMongo defaults `socketTimeoutMS` to `None` — wait forever. So a TCP connection to
Atlas that dies **without a FIN or RST** stays open as far as the driver is concerned, and the
next read on it blocks permanently. A dropped uplink, a NAT table reap and a firewall idle-reap
all produce exactly that.

Nearly every route touches Mongo, so nearly every route hung. Including `/health`, which calls
`check_database_health()` and pings the database to report `"mongodb": true`.

## The part that made it worse

`/health` needs no token, and the desktop client polls it to decide whether to fail over to the
backup backend. A `/health` that **hangs** rather than failing is the one shape that defeats
failover: the probe cannot return "unhealthy" because it cannot return. The fallback existed,
was configured, and could not fire.

A health check that can block is not a health check. It reports on a dependency, so it must never
inherit that dependency's worst case.

## The rule

A timeout on server selection is not a timeout on the operation. Any client that talks to a remote
database over a link that can vanish needs both, and the socket bound is the one that stops a hang.

Same family as [[Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]]: the
`try/except` around the ping looked like it handled failure, and caught nothing, because a hang
raises nothing.

## What was changed

- `connection.py` passes `connectTimeoutMS=10_000` and `socketTimeoutMS=30_000`. 30s is far above
  any query this app issues and far below "never".
- `health.py` wraps the ping in `asyncio.wait_for(..., 5s)` and reports `degraded` on timeout, so
  the endpoint the client polls always answers, whatever the driver does underneath.
- `tests/test_database_socket_timeouts.py` (4) pins both. The behavioural one drives
  `check_database_health` against a client whose ping never returns.

## Related

- [[Gotcha - A LAN Server Bound to the Network and Refused It]] — the same server, the previous day
- [[ADR-013 Cloud Deployment Topology with Gated CI-CD]]

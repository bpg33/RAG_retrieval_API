# Future: Synology-hosted retrieval proxy (out of scope for Phase 1)

Phase 1 runs the retrieval service on the Windows desktop and treats Qdrant and
PostgreSQL as read-only external dependencies. This document sketches a **future,
optional** deployment that would run the retrieval service (or a thin proxy) on
the Synology itself. It is explicitly **not** part of the initial build and must
not delay it.

## Why consider it later

- **Stronger read-only boundary.** If the installed Qdrant cannot issue a scoped
  read-only credential, a Synology-hosted proxy could mediate all access and
  expose only search/scroll/retrieve, keeping raw Qdrant/PostgreSQL entirely off
  the LAN surface.
- **Fewer network hops.** Co-locating retrieval with the data reduces round-trip
  latency for embedding-independent stages.
- **Central policy.** One place to enforce allowlists, budgets, and audit logging
  for multiple client devices.

## Possible shape

- Run the same container (`Dockerfile`) under Synology **Container Manager**.
- Bind it to the LAN interface only; expose the REST API to approved desktop IPs
  via the Synology firewall. Never forward the port on the router.
- Keep Qdrant/PostgreSQL bound to the Docker network / localhost so only the proxy
  reaches them.
- Continue to use the dedicated SELECT-only PostgreSQL reader and, if available,
  a read-only Qdrant credential.

## Preconditions before attempting this

1. Native Windows deployment is stable and the discovery mapping is complete.
2. Read-only verification passes end-to-end.
3. Performance baseline recorded (to compare co-located vs desktop).
4. A tested backup/rollback path for the Synology container configuration.

## Explicitly still out of scope

Remote/internet access, multi-user administration, and any write capability
remain out of scope regardless of where the service runs.

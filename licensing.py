#!/usr/bin/env python3
"""
Entitlement seam for future paid features. No accounts, server, or paid
feature exist yet, so this always returns True — it exists only so a future
gated feature has one place to plug into instead of scattering ad-hoc checks.

When server/auth infra ships (tracked in BACKLOG.md), this becomes a real
check backed by server-side entitlement verification. A client-side-only
check here would just be theater — the client can report usage, but must
never be the thing that decides.
"""


def is_licensed(feature):
    return True

"""Immutable, expiring approval requests.

An approval is bound to the *exact* action and its arguments. When a proposal is
created we:

1. Copy the arguments into a read-only mapping so they cannot be mutated later.
2. Compute a SHA-256 *fingerprint* over the action name plus the arguments.
3. Attach a random one-time ``token`` and an ``expires_at`` deadline.

An approval is therefore unforgeable in the normal flow, cannot be silently
changed, and cannot be replayed after it expires. The controller re-checks all
of these before anything runs.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


def fingerprint(action_name: str, arguments: Mapping[str, object]) -> str:
    """Return a stable hash of an action name and its arguments.

    Keys are sorted and separators are fixed so that two equal proposals always
    produce the same fingerprint, while any change to the action or to a value
    produces a different one.
    """
    payload = json.dumps(
        {"action": action_name, "arguments": dict(arguments)},
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ApprovalRequest:
    """A single, pending approval for one exact action + arguments.

    Frozen so once created it cannot be edited. ``arguments`` is additionally a
    read-only mapping.
    """

    action_name: str
    arguments: Mapping[str, object]
    token: str
    fingerprint: str
    created_at: float
    expires_at: float

    def is_expired(self, now: float) -> bool:
        """Return ``True`` when the deadline has been reached or passed."""
        return now >= self.expires_at


def create_approval(
    action_name: str,
    arguments: Mapping[str, object],
    *,
    now: float,
    ttl: float,
) -> ApprovalRequest:
    """Create a fresh approval request that lives for ``ttl`` seconds from ``now``."""
    frozen = MappingProxyType(dict(arguments))
    return ApprovalRequest(
        action_name=action_name,
        arguments=frozen,
        token=secrets.token_hex(16),
        fingerprint=fingerprint(action_name, frozen),
        created_at=now,
        expires_at=now + ttl,
    )

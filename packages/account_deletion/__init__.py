"""Account deletion core (design: specs/story-specs/spec/implementation-plan/account-deletion-design.md, rev 3).

D1 scope: the durable request record, the scheduled worker's state machine and phases, verification of late
writes, restore replay and the operator CLI. Inert: no route, no infrastructure and no deployed caller yet
(D2 adds the table, Lambda and rule; D3 adds the API routes).
"""
from .config import PHASES, DeletionConfig
from .replay import replay_after_restore
from .request_store import (
           AcceptResult,
           LeaseLost,
           RequestStore,
           public_view,
           receipt_hash,
)
from .targets import DeleteIncomplete, Targets
from .worker import Worker

__all__ = ["PHASES", "AcceptResult", "DeleteIncomplete", "DeletionConfig", "LeaseLost", "RequestStore", "Targets",
           "Worker", "public_view", "receipt_hash", "replay_after_restore"]

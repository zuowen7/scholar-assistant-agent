"""Server-owned grants binding Agent requests to an explicitly opened project."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI


@dataclass(frozen=True)
class WorkspaceGrant:
    root: Path
    expires_at: float


class WorkspaceGrantStore:
    def __init__(self, ttl_seconds: int = 24 * 60 * 60):
        self.ttl_seconds = ttl_seconds
        self._grants: dict[str, WorkspaceGrant] = {}

    def issue(self, root: str | Path) -> str:
        resolved = Path(root).resolve(strict=True)
        if not resolved.is_dir():
            raise ValueError("Workspace grant target must be a directory")
        token = secrets.token_urlsafe(32)
        self._grants[token] = WorkspaceGrant(
            root=resolved,
            expires_at=time.monotonic() + self.ttl_seconds,
        )
        return token

    def root_for_token(self, token: str) -> Path:
        grant = self._grants.get(token)
        if grant is None:
            raise ValueError("Workspace grant is missing or invalid")
        if grant.expires_at <= time.monotonic():
            self._grants.pop(token, None)
            raise ValueError("Workspace grant has expired; reopen the project")
        return grant.root

    def resolve(self, token: str, requested_root: str | Path) -> Path:
        root = self.root_for_token(token)
        requested = Path(requested_root).resolve()
        if requested != root:
            raise ValueError("Workspace grant does not match the requested project")
        return root


def install_workspace_grants(app: FastAPI) -> WorkspaceGrantStore:
    store = getattr(app.state, "agent_workspace_grants", None)
    if isinstance(store, WorkspaceGrantStore):
        return store
    store = WorkspaceGrantStore()
    app.state.agent_workspace_grants = store
    return store


def get_workspace_grants(app: FastAPI) -> WorkspaceGrantStore | None:
    store = getattr(app.state, "agent_workspace_grants", None)
    return store if isinstance(store, WorkspaceGrantStore) else None

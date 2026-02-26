"""Authentication and authorisation placeholders.

This module provides dependency-injection-based auth guards that can be
swapped out for real implementations (e.g. OAuth2 / JWT) later.

Current behaviour:
    - ``require_auth``: always passes, returns a stub user dict.
    - ``require_role``: always passes for any requested role.

To enable real auth, replace the placeholder functions and update the
``User`` model as needed.
"""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from pydantic import BaseModel

from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------


class User(BaseModel):
    """Minimal user representation returned by the auth layer.

    Attributes:
        id: Unique user identifier.
        name: Display name.
        roles: Set of role names assigned to the user.
    """

    id: str = "anonymous"
    name: str = "Anonymous User"
    roles: set[str] = {"viewer"}


# ---------------------------------------------------------------------------
# AuthN placeholder
# ---------------------------------------------------------------------------

_PLACEHOLDER_USER = User()


async def require_auth(request: Request) -> User:
    """Dependency that authenticates the current request.

    **Placeholder** — always returns an anonymous user.
    Replace this with real token validation (e.g. OAuth2 bearer)
    when ready.

    Args:
        request: The incoming HTTP request (used for header inspection).

    Returns:
        The authenticated user.
    """
    # TODO(auth): Validate Authorization header / token here.  # noqa: FIX002
    logger.debug("Auth placeholder: allowing request to %s", request.url.path)
    return _PLACEHOLDER_USER


CurrentUser = Annotated[User, Depends(require_auth)]
"""Dependency alias: inject the authenticated user into route handlers."""


# ---------------------------------------------------------------------------
# AuthZ placeholder
# ---------------------------------------------------------------------------


def require_role(*roles: str) -> Callable[..., Coroutine[Any, Any, User]]:
    """Dependency factory that checks whether the user has the required role(s).

    **Placeholder** — always passes.

    Usage::

        @router.get("/admin", dependencies=[Depends(require_role("admin"))])
        def admin_panel(): ...

    Args:
        *roles: One or more role names the user must have.

    Returns:
        A FastAPI dependency callable.
    """

    async def _check_role(user: CurrentUser) -> User:
        # TODO(auth): Enforce role check — raise HTTPException(403) on failure.  # noqa: FIX002
        logger.debug(
            "AuthZ placeholder: user=%s required_roles=%s actual_roles=%s",
            user.id,
            roles,
            user.roles,
        )
        return user

    return _check_role

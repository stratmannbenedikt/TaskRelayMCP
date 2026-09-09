from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from taskrelaymcp.config import Permission, Principal, authenticate


def current_principal(authorization: Annotated[str | None, Header()] = None) -> Principal:
    principal = authenticate(authorization)
    if not principal:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid bearer token")
    return principal


def writer(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
    if principal.permission != Permission.READ_WRITE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "READ_WRITE permission required")
    return principal


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]
Writer = Annotated[Principal, Depends(writer)]

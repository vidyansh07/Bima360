"""
Auth router — AWS Cognito integration.
/auth/agent/login  — agent login via Agent User Pool
/auth/user/login   — end-user login via User Pool
/auth/refresh      — refresh access token using refresh token

Passwords are NEVER stored here — Cognito owns credentials.
"""
import asyncio
import logging

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException, status

from backend.core.config import settings
from backend.core.responses import err, ok
from backend.schemas.schemas import LoginRequest, RefreshRequest, TokenResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])


def _cognito_client():
    return boto3.client(
        "cognito-idp",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
    )


async def _initiate_auth(client_id: str, username: str, password: str) -> dict:
    """Wrap sync boto3 call in a thread."""
    client = _cognito_client()

    def _call():
        return client.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": username, "PASSWORD": password},
            ClientId=client_id,
        )

    try:
        return await asyncio.to_thread(_call)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("NotAuthorizedException", "UserNotFoundException"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            ) from exc
        if code == "UserNotConfirmedException":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account not confirmed — verify OTP first",
            ) from exc
        logger.error("Cognito auth error: %s", exc)
        raise HTTPException(status_code=500, detail="Auth service error") from exc


async def _refresh_token(client_id: str, refresh_token: str) -> dict:
    client = _cognito_client()

    def _call():
        return client.initiate_auth(
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={"REFRESH_TOKEN": refresh_token},
            ClientId=client_id,
        )

    try:
        return await asyncio.to_thread(_call)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "NotAuthorizedException":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token invalid or expired",
            ) from exc
        raise HTTPException(status_code=500, detail="Auth service error") from exc


@router.post("/agent/login", response_model=dict)
async def agent_login(body: LoginRequest):
    """Agent login — authenticates against Agent Cognito User Pool."""
    response = await _initiate_auth(
        settings.AWS_COGNITO_CLIENT_ID,
        body.username,
        body.password,
    )
    tokens = response["AuthenticationResult"]
    return ok(
        TokenResponse(
            access_token=tokens["AccessToken"],
            id_token=tokens["IdToken"],
            refresh_token=tokens["RefreshToken"],
            expires_in=tokens["ExpiresIn"],
        ).model_dump()
    )


@router.post("/user/login", response_model=dict)
async def user_login(body: LoginRequest):
    """End-user login — authenticates against User Cognito User Pool."""
    # Note: users may have a separate ClientId if pools differ
    response = await _initiate_auth(
        settings.AWS_COGNITO_CLIENT_ID,
        body.username,
        body.password,
    )
    tokens = response["AuthenticationResult"]
    return ok(
        TokenResponse(
            access_token=tokens["AccessToken"],
            id_token=tokens["IdToken"],
            refresh_token=tokens["RefreshToken"],
            expires_in=tokens["ExpiresIn"],
        ).model_dump()
    )


@router.post("/refresh", response_model=dict)
async def refresh_token(body: RefreshRequest):
    """Refresh access token using a valid refresh token."""
    response = await _refresh_token(
        settings.AWS_COGNITO_CLIENT_ID,
        body.refresh_token,
    )
    tokens = response["AuthenticationResult"]
    return ok({
        "access_token": tokens["AccessToken"],
        "id_token": tokens.get("IdToken"),
        "expires_in": tokens["ExpiresIn"],
        "token_type": "Bearer",
    })

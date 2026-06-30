import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger

from api.constants import GOOGLE_CLIENT_ID, RESEND_API_KEY, RESEND_FROM_EMAIL, UI_APP_URL
from api.db import db_client
from api.db.models import UserModel
from api.enums import PostHogEvent
from api.schemas.auth import AuthResponse, GoogleAuthRequest, MagicLinkRequest, MagicLinkVerifyRequest, UserResponse
from api.services.auth.depends import create_user_configuration_with_mps_key, get_user
from api.services.posthog_client import capture_event
from api.utils.auth import create_jwt_token, create_magic_token, decode_magic_token

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


async def send_magic_link_email(email: str, link: str):
    if not RESEND_API_KEY:
        logger.info(
            f"\n========================================\n"
            f"RESEND_API_KEY NOT SET. MAGIC LINK FOR {email}:\n"
            f"{link}\n"
            f"========================================\n"
        )
        return

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": RESEND_FROM_EMAIL,
                    "to": email,
                    "subject": "Sign in to VCalls Ai",
                    "html": f"""
                    <p>Hello,</p>
                    <p>Click the link below to sign in to your VCalls Ai account. This link will expire in 15 minutes.</p>
                    <p><a href="{link}"><strong>Sign in to VCalls Ai</strong></a></p>
                    <p>If you did not request this link, you can safely ignore this email.</p>
                    """,
                },
            )
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to send Magic Link email to {email}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send magic link email",
            )


async def get_or_create_user_and_org(
    email: str, provider_id: str | None = None
) -> tuple[UserModel, int]:
    # Check if user exists
    user = await db_client.get_user_by_email(email)
    was_created = False
    if not user:
        # Create passwordless user
        user = await db_client.create_user_passwordless(
            email=email, provider_id=provider_id
        )
        was_created = True

    # Get or create organization
    org_provider_id = f"org_{user.provider_id}"
    organization, org_created = await db_client.get_or_create_organization_by_provider_id(
        org_provider_id=org_provider_id, user_id=user.id
    )

    # Link user to organization if not already linked
    if was_created or org_created:
        await db_client.add_user_to_organization(user.id, organization.id)
        await db_client.update_user_selected_organization(user.id, organization.id)

        # Create default service configuration
        try:
            mps_config = await create_user_configuration_with_mps_key(
                user.id, organization.id, user.provider_id
            )
            if mps_config:
                await db_client.update_user_configuration(user.id, mps_config)
        except Exception:
            logger.warning(
                "Failed to create default configuration for OSS user", exc_info=True
            )

        # Fetch user again to ensure relationships are loaded/refreshed
        user = await db_client.get_user_by_id(user.id)

    org_id = user.selected_organization_id or organization.id
    return user, org_id


@router.post("/magic-link")
async def send_magic_link(request: MagicLinkRequest):
    token = create_magic_token(request.email)
    link = f"{UI_APP_URL}/auth/callback?token={token}"
    await send_magic_link_email(request.email, link)
    return {"message": "Magic link sent successfully"}


@router.post("/magic-link/verify", response_model=AuthResponse)
async def verify_magic_link(request: MagicLinkVerifyRequest):
    try:
        email = decode_magic_token(request.token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or expired token: {str(e)}",
        )

    user, org_id = await get_or_create_user_and_org(email)
    token = create_jwt_token(user.id, user.email)

    capture_event(
        distinct_id=str(user.provider_id),
        event=PostHogEvent.SIGNED_IN,
        properties={
            "organization_id": org_id,
            "auth_provider": "magic_link",
        },
    )

    return AuthResponse(
        token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            organization_id=org_id,
            provider_id=user.provider_id,
        ),
    )


@router.post("/google", response_model=AuthResponse)
async def google_auth(request: GoogleAuthRequest):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={request.id_token}"
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error(f"Google token verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Google token",
            )

    # Verify audience if client ID is configured
    if GOOGLE_CLIENT_ID and data.get("aud") != GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Google Client ID",
        )

    email = data.get("email")
    sub = data.get("sub")
    if not email or not sub:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing email or sub in Google token",
        )

    provider_id = f"google_{sub}"
    user, org_id = await get_or_create_user_and_org(email, provider_id)
    token = create_jwt_token(user.id, user.email)

    capture_event(
        distinct_id=str(user.provider_id),
        event=PostHogEvent.SIGNED_IN,
        properties={
            "organization_id": org_id,
            "auth_provider": "google",
        },
    )

    return AuthResponse(
        token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            organization_id=org_id,
            provider_id=user.provider_id,
        ),
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user(user: UserModel = Depends(get_user)):
    return UserResponse(
        id=user.id,
        email=user.email,
        organization_id=user.selected_organization_id,
        provider_id=user.provider_id,
    )


@router.get("/config")
async def get_auth_config():
    return {
        "google_client_id": GOOGLE_CLIENT_ID,
    }


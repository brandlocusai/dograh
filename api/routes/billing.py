import os
import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, Header, Query, status
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.future import select
from sqlalchemy import func

from api.db import db_client
from api.db.models import UserModel, OrganizationModel, BillingTransactionModel
from api.services.auth.depends import get_user

router = APIRouter(prefix="/billing", tags=["billing"])

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


class CheckoutSessionRequest(BaseModel):
    amount_usd: float


class CheckoutSessionResponse(BaseModel):
    url: str


class BalanceResponse(BaseModel):
    balance_usd: float
    price_per_second_usd: float | None


class TransactionResponse(BaseModel):
    id: int
    amount_usd: float
    status: str
    stripe_session_id: str | None
    created_at: str


class TransactionsListResponse(BaseModel):
    transactions: list[TransactionResponse]
    total_count: int


@router.post("/checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    request: CheckoutSessionRequest,
    user: UserModel = Depends(get_user)
):
    if request.amount_usd < 1.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Minimum top-up amount is $1.00",
        )

    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not have an active organization",
        )

    # Get organization to verify
    org = await db_client.get_organization_by_id(org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    try:
        # Create Stripe Checkout Session
        ui_app_url = os.getenv("UI_APP_URL", "http://localhost:3000")

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": "VCall AI - Account Balance Top Up",
                            "description": f"Top up organization credits for {org.provider_id}",
                        },
                        "unit_amount": int(round(request.amount_usd * 100)),  # cents
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=f"{ui_app_url}/billing?success=true&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{ui_app_url}/billing?cancel=true",
            client_reference_id=str(org_id),
        )

        return CheckoutSessionResponse(url=session.url)
    except Exception as e:
        logger.error(f"Failed to create Stripe checkout session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stripe integration error: {str(e)}",
        )


class VerifySessionRequest(BaseModel):
    session_id: str


@router.post("/verify-session", response_model=BalanceResponse)
async def verify_session(
    request: VerifySessionRequest,
    user: UserModel = Depends(get_user)
):
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not have an active organization",
        )

    try:
        session = stripe.checkout.Session.retrieve(request.session_id)
        if not isinstance(session, dict) and hasattr(session, "to_dict"):
            session = session.to_dict()
    except Exception as e:
        logger.error(f"Failed to retrieve Stripe session {request.session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Stripe session: {str(e)}",
        )

    client_ref_id = session.get("client_reference_id")
    if not client_ref_id or int(client_ref_id) != org_id:
        logger.warning(f"Session {request.session_id} organization mismatch. Expected {org_id}, got {client_ref_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to verify this payment session",
        )

    if session.get("payment_status") != "paid":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment has not been completed for this session",
        )

    amount_total = session.get("amount_total")  # in cents
    if amount_total is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payment amount in session",
        )

    amount_usd = float(amount_total) / 100.0

    async with db_client.async_session() as db_session:
        # Check if transaction was already processed
        stmt = select(BillingTransactionModel).where(
            BillingTransactionModel.stripe_session_id == request.session_id
        )
        result = await db_session.execute(stmt)
        tx = result.scalar_one_or_none()

        if tx and tx.status == "completed":
            # Already processed, get organization to return current balance
            org = await db_client.get_organization_by_id(org_id)
            if not org:
                raise HTTPException(status_code=404, detail="Organization not found")
            return BalanceResponse(
                balance_usd=org.balance_usd,
                price_per_second_usd=org.price_per_second_usd
            )

        # Get organization with row lock
        org_stmt = select(OrganizationModel).where(OrganizationModel.id == org_id).with_for_update()
        org_result = await db_session.execute(org_stmt)
        org = org_result.scalar_one_or_none()

        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        # Update organization balance
        org.balance_usd = (org.balance_usd or 0.0) + amount_usd

        # Update or create transaction record
        if tx:
            tx.status = "completed"
        else:
            tx = BillingTransactionModel(
                organization_id=org_id,
                stripe_session_id=request.session_id,
                amount_usd=amount_usd,
                status="completed"
            )
            db_session.add(tx)

        await db_session.commit()
        logger.info(f"Successfully verified and credited organization {org_id} with ${amount_usd} via verification endpoint")

        return BalanceResponse(
            balance_usd=org.balance_usd,
            price_per_second_usd=org.price_per_second_usd
        )



@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, webhook_secret
        )
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Webhook signature verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature",
        )
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        if not isinstance(session, dict) and hasattr(session, "to_dict"):
            session = session.to_dict()
        stripe_session_id = session.get("id")
        org_id_str = session.get("client_reference_id")
        amount_total = session.get("amount_total")  # in cents

        if not stripe_session_id or not org_id_str or amount_total is None:
            logger.error("Missing required fields in Stripe session object")
            return {"status": "ignored"}

        org_id = int(org_id_str)
        amount_usd = float(amount_total) / 100.0

        logger.info(f"Fulfilling payment for Stripe Session: {stripe_session_id}, Org: {org_id}, Amount: ${amount_usd}")

        async with db_client.async_session() as db_session:
            # Check if transaction was already processed (idempotency)
            stmt = select(BillingTransactionModel).where(
                BillingTransactionModel.stripe_session_id == stripe_session_id
            )
            result = await db_session.execute(stmt)
            tx = result.scalar_one_or_none()

            if tx and tx.status == "completed":
                logger.info(f"Transaction {stripe_session_id} already completed.")
                return {"status": "already_completed"}

            # Get organization with row lock
            org_stmt = select(OrganizationModel).where(OrganizationModel.id == org_id).with_for_update()
            org_result = await db_session.execute(org_stmt)
            org = org_result.scalar_one_or_none()

            if not org:
                logger.error(f"Organization {org_id} not found for payment {stripe_session_id}")
                raise HTTPException(status_code=404, detail="Organization not found")

            # Update organization balance
            org.balance_usd = (org.balance_usd or 0.0) + amount_usd

            # Update or create transaction record
            if tx:
                tx.status = "completed"
            else:
                tx = BillingTransactionModel(
                    organization_id=org_id,
                    stripe_session_id=stripe_session_id,
                    amount_usd=amount_usd,
                    status="completed"
                )
                db_session.add(tx)

            await db_session.commit()
            logger.info(f"Successfully credited organization {org_id} with ${amount_usd}")

    return {"status": "success"}


@router.get("/balance", response_model=BalanceResponse)
async def get_balance(user: UserModel = Depends(get_user)):
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User does not have an active organization")

    org = await db_client.get_organization_by_id(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    return BalanceResponse(
        balance_usd=org.balance_usd,
        price_per_second_usd=org.price_per_second_usd
    )


@router.get("/transactions", response_model=TransactionsListResponse)
async def get_transactions(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: UserModel = Depends(get_user)
):
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User does not have an active organization")

    async with db_client.async_session() as db_session:
        # Get transactions list
        stmt = (
            select(BillingTransactionModel)
            .where(BillingTransactionModel.organization_id == org_id)
            .order_by(BillingTransactionModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db_session.execute(stmt)
        transactions = result.scalars().all()

        # Get total count
        count_stmt = (
            select(func.count(BillingTransactionModel.id))
            .where(BillingTransactionModel.organization_id == org_id)
        )
        count_result = await db_session.execute(count_stmt)
        total_count = count_result.scalar() or 0

    return TransactionsListResponse(
        transactions=[
            TransactionResponse(
                id=tx.id,
                amount_usd=tx.amount_usd,
                status=tx.status,
                stripe_session_id=tx.stripe_session_id,
                created_at=tx.created_at.isoformat()
            )
            for tx in transactions
        ],
        total_count=total_count
    )

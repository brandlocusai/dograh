from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from api.constants import OSS_JWT_EXPIRY_HOURS, OSS_JWT_SECRET


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_jwt_token(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": datetime.now(UTC) + timedelta(hours=OSS_JWT_EXPIRY_HOURS),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, OSS_JWT_SECRET, algorithm="HS256")


def decode_jwt_token(token: str) -> dict:
    return jwt.decode(token, OSS_JWT_SECRET, algorithms=["HS256"])


def create_magic_token(email: str) -> str:
    payload = {
        "sub": "magic_link",
        "email": email.lower(),
        "exp": datetime.now(UTC) + timedelta(minutes=15),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, OSS_JWT_SECRET, algorithm="HS256")


def decode_magic_token(token: str) -> str:
    payload = jwt.decode(token, OSS_JWT_SECRET, algorithms=["HS256"])
    if payload.get("sub") != "magic_link":
        raise jwt.InvalidTokenError("Invalid token subject")
    return payload["email"]

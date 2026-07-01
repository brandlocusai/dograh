import asyncio
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import select

load_dotenv("api/.env")
sys.path.append(os.path.abspath("."))

from api.db.db_client import DBClient
from api.db.models import UserModel

async def list_users():
    db = DBClient()
    async with db.async_session() as session:
        res = await session.execute(select(UserModel))
        users = res.scalars().all()
        print(f"Total Users in DB: {len(users)}")
        for u in users:
            print(f"- ID: {u.id}, Email: {u.email}, ProviderID: {u.provider_id}")

if __name__ == "__main__":
    asyncio.run(list_users())

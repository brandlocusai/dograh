import asyncio
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import select

load_dotenv("api/.env")
sys.path.append(os.path.abspath("."))

from api.db.db_client import DBClient
from api.db.models import GlobalConfigurationModel

async def show_keys():
    db = DBClient()
    async with db.async_session() as session:
        res = await session.execute(
            select(GlobalConfigurationModel).where(GlobalConfigurationModel.key == "api_keys")
        )
        obj = res.scalars().first()
        if obj:
            print("API Keys in DB:")
            for k, v in obj.value.items():
                print(f"- {k}: {v[:10]}...{v[-10:] if len(v) > 10 else ''}")
        else:
            print("No 'api_keys' entry found in database global configurations.")

if __name__ == "__main__":
    asyncio.run(show_keys())

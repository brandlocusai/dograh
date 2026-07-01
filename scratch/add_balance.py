import asyncio
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import select

# Load environment from api/.env
load_dotenv("api/.env")

# Ensure correct python path to import app services
sys.path.append(os.path.abspath("."))

from api.db.db_client import DBClient
from api.db.models import UserModel, OrganizationModel

async def add_balance():
    email = "sameer.3for4@gmail.com"
    credit_amount = 100.0
    
    print(f"Connecting to database...")
    db = DBClient()
    async with db.async_session() as session:
        # Search for user by email case-insensitively
        res = await session.execute(
            select(UserModel).where(UserModel.email.ilike(email))
        )
        user = res.scalars().first()
        
        if not user:
            print(f"Error: User with email '{email}' not found.")
            return
            
        print(f"Found user: ID={user.id}, Email={user.email}")
        
        # Get selected organization or first organization
        org_id = user.selected_organization_id
        if not org_id:
            print("User does not have selected_organization_id. Querying user's organizations...")
            # Query organization_users table
            from api.db.models import organization_users_association
            assoc_res = await session.execute(
                select(organization_users_association.c.organization_id).where(
                    organization_users_association.c.user_id == user.id
                )
            )
            org_ids = [r[0] for r in assoc_res.all()]
            if not org_ids:
                print("Error: User is not associated with any organization.")
                return
            org_id = org_ids[0]
            
        res_org = await session.execute(
            select(OrganizationModel).where(OrganizationModel.id == org_id)
        )
        org = res_org.scalars().first()
        if not org:
            print(f"Error: Organization with ID {org_id} not found.")
            return
            
        old_balance = org.balance_usd or 0.0
        new_balance = old_balance + credit_amount
        org.balance_usd = new_balance
        
        org_id_val = org.id
        await session.commit()
        print(f"Success! Credited ${credit_amount:.2f} to Organization ID {org_id_val}.")
        print(f"Previous Balance: ${old_balance:.2f} -> New Balance: ${new_balance:.2f}")

if __name__ == "__main__":
    asyncio.run(add_balance())

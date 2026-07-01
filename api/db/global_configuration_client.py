from typing import Any, Optional
from sqlalchemy.future import select

from api.db.base_client import BaseDBClient
from api.db.models import GlobalConfigurationModel


class GlobalConfigurationClient(BaseDBClient):
    async def get_global_configuration(
        self, key: str
    ) -> Optional[GlobalConfigurationModel]:
        """Get a specific global configuration by key."""
        async with self.async_session() as session:
            result = await session.execute(
                select(GlobalConfigurationModel).where(
                    GlobalConfigurationModel.key == key,
                )
            )
            return result.scalars().first()

    async def upsert_global_configuration(
        self, key: str, value: Any
    ) -> GlobalConfigurationModel:
        """Create or update a global configuration."""
        async with self.async_session() as session:
            result = await session.execute(
                select(GlobalConfigurationModel).where(
                    GlobalConfigurationModel.key == key,
                )
            )
            config = result.scalars().first()

            if config:
                config.value = value
            else:
                config = GlobalConfigurationModel(
                    key=key,
                    value=value,
                )
                session.add(config)

            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e
            await session.refresh(config)
            return config

    async def get_global_configuration_value(
        self, key: str, default: Any = None
    ) -> Any:
        """Get the value of a global configuration, returning default if not found."""
        config = await self.get_global_configuration(key)
        return config.value if config else default

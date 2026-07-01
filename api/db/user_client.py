import uuid
from datetime import datetime, timezone

from loguru import logger
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.future import select

from api.db.base_client import BaseDBClient
from api.db.models import UserConfigurationModel, UserModel
from api.schemas.user_configuration import UserConfiguration


class UserClient(BaseDBClient):
    async def get_or_create_user_by_provider_id(
        self, provider_id: str
    ) -> tuple[UserModel, bool]:
        """Return (user, was_created) tuple."""
        async with self.async_session() as session:
            # First try to get existing user
            result = await session.execute(
                select(UserModel).where(UserModel.provider_id == provider_id)
            )
            user = result.scalars().first()

            if user is not None:
                return user, False

            # Use PostgreSQL's INSERT ... ON CONFLICT DO NOTHING
            # This is atomic and handles race conditions at the database level
            from sqlalchemy.dialects.postgresql import insert

            stmt = insert(UserModel.__table__).values(
                provider_id=provider_id,
                created_at=datetime.now(timezone.utc),
                selected_organization_id=None,  # Will be set later
                is_superuser=False,  # Default value
            )
            # ON CONFLICT DO NOTHING - if another request already inserted, this becomes a no-op
            stmt = stmt.on_conflict_do_nothing(index_elements=["provider_id"])

            result = await session.execute(stmt)
            await session.commit()
            was_created = result.rowcount > 0

            # Now fetch the user (either the one we just created or the one that existed)
            result = await session.execute(
                select(UserModel).where(UserModel.provider_id == provider_id)
            )
            user = result.scalars().first()

            if user is None:
                # This should never happen, but handle it just in case
                error_msg = (
                    f"Failed to create or fetch user with provider_id {provider_id}"
                )
                raise ValueError(error_msg)
        return user, was_created

    async def get_user_by_id(self, user_id: int) -> UserModel | None:
        """Fetch a user by their internal ID."""
        async with self.async_session() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            return result.scalars().first()

    async def get_user_configurations(self, user_id: int) -> UserConfiguration:
        async with self.async_session() as session:
            result = await session.execute(
                select(UserConfigurationModel).where(
                    UserConfigurationModel.user_id == user_id
                )
            )
            configuration_obj = result.scalars().first()

            # Load global default models
            from api.db.models import GlobalConfigurationModel
            from api.services.configuration.registry import REGISTRY, ServiceType
            
            default_models = {}
            try:
                global_res = await session.execute(
                    select(GlobalConfigurationModel).where(
                        GlobalConfigurationModel.key == "default_models"
                    )
                )
                global_config_obj = global_res.scalars().first()
                if global_config_obj:
                    default_models = global_config_obj.value
            except Exception as e:
                logger.warning(
                    f"Could not load global default models from DB: {e}. Using fallback defaults."
                )

            if not default_models:
                default_models = {
                    "llm_provider": "openrouter",
                    "llm_model": "openai/gpt-4o",
                    "stt_provider": "deepgram",
                    "stt_model": "nova-2",
                    "tts_provider": "elevenlabs",
                    "tts_model": "default",
                }

            config_data = {}
            if configuration_obj and isinstance(configuration_obj.configuration, dict):
                import copy
                config_data = copy.deepcopy(configuration_obj.configuration)

            service_type_map = {
                "llm": ServiceType.LLM,
                "tts": ServiceType.TTS,
                "stt": ServiceType.STT,
            }

            for section in ["llm", "tts", "stt"]:
                if section not in config_data or not isinstance(config_data[section], dict):
                    config_data[section] = {}
                
                # Fallback to default provider/model if not configured
                active_provider = config_data[section].get("provider")
                if not active_provider:
                    default_provider = default_models.get(f"{section}_provider")
                    if default_provider:
                        config_data[section]["provider"] = default_provider
                        active_provider = default_provider
                
                if active_provider:
                    current_model = config_data[section].get("model")
                    if not current_model or current_model == "default":
                        # Only set model if active provider is the default provider
                        default_provider = default_models.get(f"{section}_provider")
                        if active_provider == default_provider:
                            default_model = default_models.get(f"{section}_model")
                            if default_model and default_model != "default":
                                config_data[section]["model"] = default_model

                    # Inject defaults for other required fields from registry
                    config_cls = REGISTRY[service_type_map[section]].get(active_provider)
                    if config_cls:
                        for field_name, field_def in config_cls.model_fields.items():
                            if field_name not in config_data[section] and field_def.default is not None:
                                config_data[section][field_name] = field_def.default
                        if section == "tts" and "voice_id" in config_cls.model_fields and "voice_id" not in config_data[section]:
                            config_data[section]["voice_id"] = "21m00Tcm4TlvDq8ikWAM"
                    
                    # Inject admin configured global default overrides for properties
                    for key_name in ["base_url", "max_tokens", "voice_id", "language"]:
                        global_key = f"{section}_{key_name}"
                        if global_key in default_models:
                            # User hasn't overridden it, inject admin default value
                            if key_name not in config_data[section]:
                                config_data[section][key_name] = default_models[global_key]
                    
                    # Inject tts_voice_id as 'voice' field too (ElevenLabs, Deepgram TTS use 'voice')
                    if section == "tts" and "tts_voice_id" in default_models:
                        voice_id_val = default_models["tts_voice_id"]
                        if voice_id_val and "voice" not in config_data[section]:
                            config_data[section]["voice"] = voice_id_val

            # Load global API keys configuration from database
            global_api_keys = {}
            try:
                keys_res = await session.execute(
                    select(GlobalConfigurationModel).where(
                        GlobalConfigurationModel.key == "api_keys"
                    )
                )
                keys_obj = keys_res.scalars().first()
                if keys_obj:
                    global_api_keys = keys_obj.value
            except Exception as e:
                logger.warning(
                    f"Could not load global API keys from DB: {e}."
                )

            # Inject admin-managed api_key for the chosen provider if not set
            for section in ["llm", "tts", "stt"]:
                if section in config_data and isinstance(config_data[section], dict):
                    sect_provider = config_data[section].get("provider")
                    if sect_provider:
                        sect_type = service_type_map[section]
                        config_cls = REGISTRY[sect_type].get(sect_provider)
                        if config_cls and "api_key" in config_cls.model_fields:
                            admin_key = global_api_keys.get(sect_provider)
                            if not admin_key:
                                import os
                                env_key_name = f"{sect_provider.upper()}_API_KEY"
                                admin_key = os.getenv(env_key_name)
                            if admin_key:
                                config_data[section]["api_key"] = admin_key
                            elif "api_key" not in config_data[section]:
                                # Fallback to a placeholder key to prevent Pydantic validation errors in test environments
                                config_data[section]["api_key"] = "dummy-key"

            try:
                return UserConfiguration.model_validate(
                    {
                        **config_data,
                        "last_validated_at": configuration_obj.last_validated_at if configuration_obj else None,
                    }
                )
            except ValidationError as e:
                # If configuration contains an unsupported provider,
                # return a default configuration without failing
                logger.warning(
                    f"Failed to validate user configuration for user {user_id}: {e}. "
                    "Returning default configuration."
                )
                return UserConfiguration()

    async def update_user_configuration(
        self, user_id: int, configuration: UserConfiguration
    ) -> UserConfiguration:
        async with self.async_session() as session:
            result = await session.execute(
                select(UserConfigurationModel).where(
                    UserConfigurationModel.user_id == user_id
                )
            )
            configuration_obj = result.scalars().first()
            # Strip any user-supplied api keys or secrets before saving
            config_dict = configuration.model_dump()
            for section in ["llm", "tts", "stt", "realtime", "embeddings"]:
                if section in config_dict and isinstance(config_dict[section], dict):
                    config_dict[section].pop("api_key", None)
                    config_dict[section].pop("aws_access_key", None)
                    config_dict[section].pop("aws_secret_key", None)

            if not configuration_obj:
                configuration_obj = UserConfigurationModel(
                    user_id=user_id, configuration=config_dict
                )
                session.add(configuration_obj)
            else:
                configuration_obj.configuration = config_dict
            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e
            await session.refresh(configuration_obj)
        # Update last_validated_at from the database just in case it changed
        configuration.last_validated_at = configuration_obj.last_validated_at
        return configuration

    async def update_user_configuration_last_validated_at(self, user_id: int) -> None:
        async with self.async_session() as session:
            result = await session.execute(
                select(UserConfigurationModel).where(
                    UserConfigurationModel.user_id == user_id
                )
            )
            configuration_obj = result.scalars().first()
            if not configuration_obj:
                raise ValueError(f"User configuration with ID {user_id} not found")
            configuration_obj.last_validated_at = datetime.now()
            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e
            await session.refresh(configuration_obj)

    async def update_user_selected_organization(
        self, user_id: int, organization_id: int
    ) -> None:
        """Update the user's selected organization ID."""
        async with self.async_session() as session:
            from sqlalchemy import update

            # Use a direct UPDATE statement to avoid race conditions
            # This is atomic at the database level
            stmt = (
                update(UserModel)
                .where(UserModel.id == user_id)
                .values(selected_organization_id=organization_id)
            )

            result = await session.execute(stmt)

            if result.rowcount == 0:
                raise ValueError(f"User with ID {user_id} not found")

            await session.commit()

    async def update_user_email(self, user_id: int, email: str) -> None:
        """Update the user's email address."""
        async with self.async_session() as session:
            from sqlalchemy import update

            stmt = (
                update(UserModel)
                .where(UserModel.id == user_id)
                .values(email=email.lower())
            )
            await session.execute(stmt)
            await session.commit()

    async def get_user_by_email(self, email: str) -> UserModel | None:
        """Fetch a user by their email address (case-insensitive).

        Email addresses are case-insensitive in practice, so a user who
        signed up as "User@example.com" must still be found when they later
        log in as "user@example.com". Compare on lower(email) so lookups are
        robust to capitalization differences across sign-in flows.
        """
        normalized_email = email.lower()
        async with self.async_session() as session:
            result = await session.execute(
                select(UserModel).where(func.lower(UserModel.email) == normalized_email)
            )
            return result.scalars().first()

    async def create_user_with_email(
        self, email: str, password_hash: str, name: str | None = None
    ) -> UserModel:
        """Create a new user with email and password hash."""
        async with self.async_session() as session:
            user = UserModel(
                provider_id=f"oss_{int(datetime.now(timezone.utc).timestamp())}_{uuid.uuid4()}",
                email=email.lower(),
                password_hash=password_hash,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def create_user_passwordless(
        self, email: str, provider_id: str | None = None
    ) -> UserModel:
        """Create a new passwordless user."""
        async with self.async_session() as session:
            user = UserModel(
                provider_id=provider_id or f"oss_{int(datetime.now(timezone.utc).timestamp())}_{uuid.uuid4()}",
                email=email.lower(),
                password_hash=None,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

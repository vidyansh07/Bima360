"""
Central settings — every env var in one place.
All other files import `settings` from here.
Never use os.getenv() anywhere else in the project.
"""
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    ENVIRONMENT: str = "development"
    APP_NAME: str = "Bima360 API"
    APP_VERSION: str = "1.0.0"

    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        if self.ENVIRONMENT == "development":
            return ["http://localhost:3000", "http://127.0.0.1:3000"]
        return ["https://bima360.in", "https://www.bima360.in"]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://bima360:bima360pass@localhost:5432/bima360"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # Sarvam AI (primary)
    SARVAM_API_KEY: str = ""
    SARVAM_TTS_MODEL: str = "bulbul-v2"

    # Groq (fallback)
    GROQ_API_KEY: str = ""

    # AWS
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ap-south-1"
    AWS_S3_BUCKET: str = "bima360-docs"
    AWS_COGNITO_AGENT_POOL_ID: str = ""
    AWS_COGNITO_USER_POOL_ID: str = ""
    AWS_COGNITO_CLIENT_ID: str = ""

    # Fabric
    FABRIC_CONNECTION_PROFILE_PATH: str = "./blockchain/network/connection-profile.json"
    FABRIC_WALLET_PATH: str = "./blockchain/wallets"
    FABRIC_CHANNEL_NAME: str = "bima-channel"
    FABRIC_POLICY_CHAINCODE: str = "policy"
    FABRIC_CLAIM_CHAINCODE: str = "claim"
    FABRIC_MSP_ID: str = "Bima360Org1MSP"

    # Payments
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    CASHFREE_APP_ID: str = ""
    CASHFREE_SECRET_KEY: str = ""

    # SMS
    MSG91_API_KEY: str = ""
    MSG91_SENDER_ID: str = "BIMA360"
    MSG91_TEMPLATE_OTP: str = ""

    # IPFS
    PINATA_API_KEY: str = ""
    PINATA_SECRET_KEY: str = ""

    # GCP
    GCP_PROJECT_ID: str = ""
    GCP_SA_KEY_PATH: str = "./infra/gcp-sa-key.json"

    # Monitoring
    SENTRY_DSN: str = ""

    # Rate limits / TTLs
    AI_RATE_LIMIT_PER_HOUR: int = 100
    BOT_SESSION_TTL_SECONDS: int = 1800
    RISK_CACHE_TTL_SECONDS: int = 86400
    BOT_MAX_HISTORY_MESSAGES: int = 10


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

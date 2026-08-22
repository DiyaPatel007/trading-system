
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", protected_namespaces=())

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "trading"
    postgres_user: str = "trading_user"
    postgres_password: str = "changeme"

    default_capital: float = 100_000.0
    max_risk_pct_per_trade: float = 0.5

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
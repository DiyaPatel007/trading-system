from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", protected_namespaces=())

    postgres_host: str = "localhost"  # NOTE: defaults to localhost, not "postgres" --
    postgres_port: int = 5432          # this server typically runs OUTSIDE Docker (launched
    postgres_db: str = "trading"       # directly by Claude Desktop/Code as a subprocess), so
    postgres_user: str = "trading_user"  # it needs to reach Postgres via the port you exposed
    postgres_password: str = "changeme"  # on the host (5432:5432 in docker-compose.yml), not
                                          # the internal Docker network hostname.

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
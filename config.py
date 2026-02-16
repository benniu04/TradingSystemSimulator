from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "trader"
    db_password: str = "trader"
    db_name: str = "trading"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Market data
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    use_synthetic_feed: bool = True

    # Risk
    max_position_size: float = 10000.0
    max_order_value: float = 5000.0
    max_drawdown_pct: float = 0.05

    # Logging
    log_level: str = "INFO"

    @property
    def db_dsn(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def get_settings() -> Settings:
    return Settings()

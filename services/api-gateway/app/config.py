from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """See docs/09-deployment.md #9.4 for the meaning of each variable."""

    database_url: str = "postgresql+asyncpg://keso:keso@localhost:5432/keso"

    # Self-issued JWT auth -- see docs/07-security-auth.md #7.1-7.2. There is
    # no external identity provider; this secret signs every access token
    # this deployment issues, so it must be a long random value set per
    # environment (never reused, never committed) -- see infra/.env.example.
    jwt_secret: str = "insecure-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "keso-ai"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_hours: int = 8

    opa_url: str = "http://localhost:8181"
    orchestrator_url: str = "http://localhost:8200"
    log_level: str = "INFO"

    # docs/03-api-specification.md #3.5
    chat_rate_limit: str = "30/minute"
    read_rate_limit: str = "120/minute"

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()

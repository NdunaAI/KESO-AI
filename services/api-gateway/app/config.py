from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """See docs/09-deployment.md #9.4 for the meaning of each variable."""

    database_url: str = "postgresql+asyncpg://keso:keso@localhost:5432/keso"
    keycloak_issuer: str = "http://localhost:8081/realms/keso"
    keycloak_jwks_url: str = "http://localhost:8081/realms/keso/protocol/openid-connect/certs"
    keycloak_audience: str = "keso-api-gateway"
    opa_url: str = "http://localhost:8181"
    orchestrator_url: str = "http://localhost:8200"
    log_level: str = "INFO"

    # docs/03-api-specification.md #3.5
    chat_rate_limit: str = "30/minute"
    read_rate_limit: str = "120/minute"

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()

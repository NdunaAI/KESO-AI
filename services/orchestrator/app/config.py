from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """See docs/09-deployment.md #9.4 and docs/06-rag-pipeline.md #6.4."""

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "keso_documents"
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "llama3.1:8b-instruct"
    embedding_model: str = "nomic-embed-text"
    mcp_registry: str = "/app/shared/schemas/mcp-registry.yaml"
    system_prompt_path: str = "/app/shared/prompts/system_prompt.md"
    retrieval_top_k: int = 8
    retrieval_final_k: int = 5
    max_mcp_calls_per_query: int = 4
    log_level: str = "INFO"

    model_config = {"case_sensitive": False}


settings = Settings()

.PHONY: up down logs pull-models ingest test-api test-orchestrator test-opa

up:
	docker compose -f infra/docker-compose.yml --env-file .env up -d

down:
	docker compose -f infra/docker-compose.yml down

logs:
	docker compose -f infra/docker-compose.yml logs -f

pull-models:
	docker compose -f infra/docker-compose.yml exec ollama ollama pull $${LLM_MODEL:-llama3.1:8b-instruct}
	docker compose -f infra/docker-compose.yml exec ollama ollama pull $${EMBEDDING_MODEL:-nomic-embed-text}

ingest:
	docker compose -f infra/docker-compose.yml run --rm ingestion python -m app.run_full_index

test-api:
	cd services/api-gateway && python -m pytest tests -v

test-orchestrator:
	cd services/orchestrator && python -m pytest tests -v

test-opa:
	opa test infra/opa/policies -v

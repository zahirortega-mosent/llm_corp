.PHONY: up down restart logs status test ingest pull-model

up:
	docker compose up --build -d

down:
	docker compose down

restart:
	docker compose down && docker compose up --build -d

logs:
	docker compose logs -f --tail=200

status:
	docker compose ps

test:
	bash ./scripts/test-stack.sh

ingest:
	bash ./scripts/ingest.sh

pull-model:
	bash ./scripts/pull-model.sh

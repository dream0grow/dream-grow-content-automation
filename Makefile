.PHONY: dev up down logs migrate seed test web api worker shell-api

dev: up

up:
	docker compose -f infra/docker-compose.yml up --build

down:
	docker compose -f infra/docker-compose.yml down

logs:
	docker compose -f infra/docker-compose.yml logs -f --tail=100

migrate:
	docker compose -f infra/docker-compose.yml run --rm api \
		alembic -c infra/alembic.ini upgrade head

seed:
	docker compose -f infra/docker-compose.yml run --rm api \
		python -m apps.api.scripts.seed

shell-api:
	docker compose -f infra/docker-compose.yml exec api bash

test:
	docker compose -f infra/docker-compose.yml run --rm api pytest -q

web-install:
	cd apps/web && npm install

web-dev:
	cd apps/web && npm run dev

COMPOSE_DEV = docker compose -f infra/compose/compose.dev.yml --env-file infra/env/.env.dev.example

.PHONY: dev-up dev-up-apps dev-down api-test worker-test migration-test dry-run import-only

dev-up:
	$(COMPOSE_DEV) up -d

dev-up-apps:
	$(COMPOSE_DEV) --profile apps up -d

dev-down:
	$(COMPOSE_DEV) down -v

api-test:
	python3 -m pytest apps/api/tests

worker-test:
	python3 -m pytest workflows/tests

migration-test:
	python3 -m pytest migrations/tests

dry-run:
	python3 -m migrations.dry_run backend/uploads

import-only:
	python3 -m migrations.import_only backend/uploads sqlite:///tmp/mirofish_import_only.db

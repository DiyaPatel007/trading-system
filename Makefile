.PHONY: up down logs health test-schemas ps

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

ps:
	docker compose ps

health:
	curl -s http://localhost:8000/health | python3 -m json.tool

test-schemas:
	cd libs/schemas && pip install -e . -q && cd ../.. && python3 -m pytest tests/test_schemas.py -v

.PHONY: up down reset logs test lint build verify

up:
	docker compose up --build -d

down:
	docker compose down

reset:
	docker compose down -v

logs:
	docker compose logs -f --tail=100

test:
	python -m pytest

lint:
	ruff check .

build:
	docker compose build

verify:
	python tests/integration/verify_stack.py


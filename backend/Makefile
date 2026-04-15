install:
	uv sync

dev:
	PYTHONPATH=. uv run python dev_launcher.py langgraph

gateway:
	PYTHONPATH=. uv run python dev_launcher.py gateway

test:
	PYTHONPATH=. uv run pytest tests/ -v

lint:
	uvx ruff check .
	uvx ruff format --check .

format:
	uvx ruff check . --fix && uvx ruff format .

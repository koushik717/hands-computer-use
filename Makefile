.PHONY: install test demo replay

install:
	uv sync --python 3.12 --extra dev
	uv run playwright install chromium

test:
	uv run pytest -q

demo:
	uv run hands demo

discover:
	uv run hands demo --discovery

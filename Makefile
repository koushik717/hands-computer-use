.PHONY: install test demo replay

install:
	uv sync --python 3.12 --extra dev
	uv run playwright install chromium

test:
	uv run pytest -q

demo:
	uv run hands demo

discover:
	uv run hands discover --goal "Look up member 12345 and read their current regular share balance"

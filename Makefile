install:
	uv sync

run:
	uv run chainlit run src/main.py -w

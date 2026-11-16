run:
	uv run chainlit run src/main.py -w

install:
	uv sync

test:
	uv run pytest tests -q

# Site de demonstração: compila o React e serve tudo em http://localhost:8001
site:
	cd web && npm install && npm run build
	uv run uvicorn web_api:app --app-dir src --port 8001

# Desenvolvimento do site: API na 8001 e Vite na 5173 (rodar em dois terminais)
api:
	uv run uvicorn web_api:app --app-dir src --port 8001 --reload

web:
	cd web && npm run dev

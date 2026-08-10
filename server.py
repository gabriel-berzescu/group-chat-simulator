import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

OLLAMA_URL = "http://localhost:11434"

app = FastAPI(title="Group Chat Simulator")


@app.get("/api/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
            models = [m["name"] for m in response.json().get("models", [])]
        return {"status": "ok", "ollama": "up", "models": models}
    except httpx.HTTPError:
        return {"status": "degraded", "ollama": "down", "models": []}


app.mount("/", StaticFiles(directory="static", html=True), name="static")

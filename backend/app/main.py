from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import collect, evolution, graph, match, pages, review
from app.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pages.router)
app.include_router(graph.router)
app.include_router(collect.router)
app.include_router(evolution.router)
app.include_router(match.router)
app.include_router(review.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

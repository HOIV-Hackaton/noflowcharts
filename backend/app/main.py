"""FastAPI entrypoint — skeleton.

This is intentionally minimal. Build your own API here for the frontend to call,
and consume the Phoenix ERP mock from your backend (see docs/phoenix-openapi.yaml).
Keep the ERP token and the SSH key on the backend — never in the browser.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="techbold AI Service Desk Autopilot — Team Backend", lifespan=lifespan)

# Open CORS for local dev so your React app can call this backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok"}

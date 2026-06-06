"""FastAPI entrypoint — skeleton.

This is intentionally minimal. Build your own API here for the frontend to call,
and consume the Phoenix ERP mock from your backend (see docs/phoenix-openapi.yaml).
Keep the ERP token and the SSH key on the backend — never in the browser.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_activity import router as activity_router
from app.api.routes_runs import router as runs_router
from app.api.routes_terminal import router as terminal_router
from app.api.routes_tickets import router as tickets_router
from app.api.routes_ws import router as ws_router
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

app.include_router(tickets_router)
app.include_router(runs_router)
app.include_router(activity_router)
app.include_router(ws_router)
app.include_router(terminal_router)


@app.get("/health")
def health():
    return {"status": "ok"}

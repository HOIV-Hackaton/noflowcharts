from fastapi import APIRouter

from app.api.routes_activity import router as activity_router
from app.api.routes_knowledge import router as knowledge_router
from app.api.routes_metrics import router as metrics_router
from app.api.routes_runs import router as runs_router
from app.api.routes_terminal import router as terminal_router
from app.api.routes_tickets import router as tickets_router
from app.api.routes_ws import router as ws_router


api_router = APIRouter()
api_router.include_router(tickets_router)
api_router.include_router(runs_router)
api_router.include_router(activity_router)
api_router.include_router(ws_router)
api_router.include_router(terminal_router)
api_router.include_router(metrics_router)
api_router.include_router(knowledge_router)

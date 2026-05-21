from fastapi import APIRouter

from app.api.routes import projects, reports, strategies, tasks, wallets

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(strategies.router, prefix="/strategies", tags=["strategies"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(wallets.router, prefix="/wallets", tags=["wallets"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])

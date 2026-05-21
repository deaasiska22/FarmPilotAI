from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import ProjectServiceDep
from app.models.schemas import ProjectCreate, ProjectRead

router = APIRouter()


class ScanRequest(BaseModel):
    urls: list[str]


@router.post("/scan", response_model=list[ProjectRead])
async def scan_projects(req: ScanRequest, svc: ProjectServiceDep) -> list[ProjectRead]:
    if not req.urls:
        raise HTTPException(status_code=400, detail="urls cannot be empty")
    return await svc.scan(req.urls)


@router.get("", response_model=list[ProjectRead])
async def list_projects(svc: ProjectServiceDep) -> list[ProjectRead]:
    return await svc.list_projects()


@router.post("", response_model=ProjectRead, status_code=201)
async def create_project(payload: ProjectCreate, svc: ProjectServiceDep) -> ProjectRead:
    return await svc.create(payload)

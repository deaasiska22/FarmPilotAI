"""FastAPI dependencies pulled from the global :class:`Container`."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.config import Settings
from app.container import Container, get_container
from app.services.execution_service import ExecutionService
from app.services.project_service import ProjectService
from app.services.strategy_service import StrategyService


def get_app_container() -> Container:
    return get_container()


def get_settings_dep(container: Container = Depends(get_app_container)) -> Settings:
    return container.settings


def get_project_service(container: Container = Depends(get_app_container)) -> ProjectService:
    return ProjectService(container)


def get_strategy_service(container: Container = Depends(get_app_container)) -> StrategyService:
    return StrategyService(container)


def get_execution_service(container: Container = Depends(get_app_container)) -> ExecutionService:
    return ExecutionService(container)


ContainerDep = Annotated[Container, Depends(get_app_container)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
StrategyServiceDep = Annotated[StrategyService, Depends(get_strategy_service)]
ExecutionServiceDep = Annotated[ExecutionService, Depends(get_execution_service)]

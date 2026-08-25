# Path: routes/__init__.py
# Description: Aggregate router for every Oliver API route.

from fastapi import APIRouter

from .assessment import router as assessment_router
from .email import router as email_router
from .health import router as health_router
from .lifecycle import router as lifecycle_router
from .operations import router as operations_router
from .portfolio import router as portfolio_router
from .scout import router as scout_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(assessment_router)
api_router.include_router(email_router)
api_router.include_router(lifecycle_router)
api_router.include_router(operations_router)
api_router.include_router(portfolio_router)
api_router.include_router(scout_router)

main_router = APIRouter()
main_router.include_router(health_router)
main_router.include_router(api_router)

__all__ = ["main_router"]

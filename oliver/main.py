"""FastAPI application for the Oliver backend."""

import time
import tomllib
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from config import get_settings
from logger import get_logger
from routes import main_router
from utils import request_context

settings = get_settings()
logger = get_logger()

with open("pyproject.toml", "rb") as file:
    config = tomllib.load(file)


app = FastAPI(
    title=config["project"]["name"],
    description=config["project"]["description"],
    version=config["project"]["version"],
    openapi_url="/api/openapi.json" if settings.ENV == "development" else None,
    docs_url="/api/docs" if settings.ENV == "development" else None,
    redoc_url="/api/redoc" if settings.ENV == "development" else None,
)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Add request correlation, timing headers, and completion logs."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request_context.set_request_context(endpoint=request.url.path, method=request.method)
        try:
            started_at = time.perf_counter()
            response: Response = await call_next(request)
            process_time = time.perf_counter() - started_at

            response.headers["X-Oliver-Process-Time"] = str(process_time)
            response.headers["X-Oliver-Request-Id"] = request_id
            logger.info(f"Request completed: {request.method} {request.url.path} - Status: {response.status_code} - Time: {process_time:.3f}s")
            return response
        finally:
            request_context.clear_request_context()


app.add_middleware(RequestLoggingMiddleware)
app.include_router(main_router)

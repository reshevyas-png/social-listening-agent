import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from routes import health, analyze, scans
from scheduler.setup import init_scheduler, shutdown_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(
    title="Social Listening Agent",
    version="0.2.0",
    docs_url="/docs",
    lifespan=lifespan,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.localtechedge.com",
        "https://localtechedge.com",
        "https://ai-agent-md.com",
        "http://localhost:3000",
    ],
    allow_methods=["POST", "GET"],
    allow_headers=["X-API-Key", "Content-Type"],
)

app.include_router(health.router)
app.include_router(analyze.router, prefix="/api/v1")
app.include_router(scans.router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

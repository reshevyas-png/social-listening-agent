from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from routes import health, analyze


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app = FastAPI(
    title="Social Listening Agent",
    version="0.1.0",
    docs_url="/docs",
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

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

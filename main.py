from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import health, analyze

app = FastAPI(
    title="Social Listening Agent",
    version="0.1.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["X-API-Key", "Content-Type"],
)

app.include_router(health.router)
app.include_router(analyze.router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

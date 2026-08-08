from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from loguru import logger

from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.logging_config import configure_logging
from app.api.routes import router

settings = get_settings()
configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 TRACE_PD backend starting [{settings.ENVIRONMENT}]")
    yield
    logger.info("🛑 TRACE_PD backend stopped")


app = FastAPI(
    title="TRACE_PD — Personal Behavior Debugger API",
    description=(
        "Multi-agent AI system (LangGraph) with statistical causal heuristics, "
        "IsolationForest loop detection, and real-time WebSocket alerts.\n\n"
        "**Demo:** `demo@trace.dev` / `demo1234`"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.method} {request.url.path}: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(router)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "app": "TRACE_PD", "version": settings.APP_VERSION}


@app.get("/", tags=["Health"])
async def root():
    return {"app": "TRACE_PD", "docs": "/docs", "health": "/health"}

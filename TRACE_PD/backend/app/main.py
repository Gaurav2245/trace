from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.core.config import get_settings
from app.api.routes import router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 TRACE_PD backend starting [{settings.ENVIRONMENT}]")
    yield
    logger.info("🛑 TRACE_PD backend stopped")


app = FastAPI(
    title="TRACE_PD — Personal Behavior Debugger API",
    description=(
        "Multi-agent AI system (LangGraph) with causal inference (DoWhy + EconML), "
        "IsolationForest loop detection, and real-time WebSocket alerts.\n\n"
        "**Demo:** `demo@trace.dev` / `demo1234`"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "app": "TRACE_PD", "version": settings.APP_VERSION}


@app.get("/", tags=["Health"])
async def root():
    return {"app": "TRACE_PD", "docs": "/docs", "health": "/health"}

import sys
from pathlib import Path
from loguru import logger

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    is_prod = settings.ENVIRONMENT == "production"

    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO" if is_prod else "DEBUG",
        serialize=is_prod,
        backtrace=False,
        diagnose=not is_prod,
    )

    # Relative to CWD, which is the backend root in both local dev
    # (`cd backend && uvicorn ...`) and Docker (WORKDIR /app).
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "trace_pd.log",
        level="INFO",
        rotation="10 MB",
        retention="14 days",
        compression="zip",
        serialize=True,
        backtrace=False,
        diagnose=False,
    )

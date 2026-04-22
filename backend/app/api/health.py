"""Health check endpoint."""

from fastapi import APIRouter

from .schemas import HealthOut

router = APIRouter(tags=["system"])


@router.get("/api/health", response_model=HealthOut)
async def health_check() -> HealthOut:
    """Return a simple health status for Docker/deployment probes."""
    return HealthOut(status="ok")

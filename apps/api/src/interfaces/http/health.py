from fastapi import APIRouter

from src.shared.schemas import HealthStatus

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthStatus)
def get_health() -> HealthStatus:
    return HealthStatus(
        status="ok",
        service="mirofish-novel-api-v2",
        version="0.1.0",
    )

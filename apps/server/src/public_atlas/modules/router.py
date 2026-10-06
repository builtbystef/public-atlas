from fastapi import APIRouter

from public_atlas.modules.health.router import router as health_router

router = APIRouter()
router.include_router(health_router)

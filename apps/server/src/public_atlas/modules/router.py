from fastapi import APIRouter

from public_atlas.modules.assignments.router import router as assignments_router
from public_atlas.modules.countries.router import router as countries_router
from public_atlas.modules.health.router import router as health_router
from public_atlas.modules.review.router import router as review_router

router = APIRouter()
router.include_router(health_router)
router.include_router(countries_router)
router.include_router(review_router)
router.include_router(assignments_router)

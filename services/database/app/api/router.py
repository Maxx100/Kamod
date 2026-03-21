from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.events import router as events_router
from app.api.routes.users import router as users_router


api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(events_router)

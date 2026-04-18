from fastapi import APIRouter

from app.api.endpoints import auth, health, status, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(status.router)
api_router.include_router(users.router)

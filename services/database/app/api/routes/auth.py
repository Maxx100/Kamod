from fastapi import APIRouter, status

from app.api.dependencies import UserServiceDep
from app.schemas.user import UserRegisterRequest, UserResponse


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(
    payload: UserRegisterRequest,
    service: UserServiceDep,
) -> UserResponse:
    return service.register_user(payload)

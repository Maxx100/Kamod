from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import CurrentUserId, EventServiceDep, RegistrationServiceDep, UserServiceDep
from app.schemas.event import CreatedEventsQueryParams, EventListResponse, RegisteredEventListResponse, RegisteredEventsQueryParams
from app.schemas.user import UserResponse, UserUpdateRequest


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: UUID,
    current_user_id: CurrentUserId,
    service: UserServiceDep,
) -> UserResponse:
    return service.get_user(user_id, current_user_id)


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: UUID,
    payload: UserUpdateRequest,
    current_user_id: CurrentUserId,
    service: UserServiceDep,
) -> UserResponse:
    return service.update_user(user_id, current_user_id, payload)


@router.get("/{user_id}/registered-events", response_model=RegisteredEventListResponse)
def get_registered_events(
    user_id: UUID,
    current_user_id: CurrentUserId,
    service: RegistrationServiceDep,
    params: Annotated[RegisteredEventsQueryParams, Depends()],
) -> RegisteredEventListResponse:
    return service.list_user_registered_events(user_id, current_user_id, params)


@router.get("/{user_id}/created-events", response_model=EventListResponse)
def get_created_events(
    user_id: UUID,
    service: EventServiceDep,
    params: Annotated[CreatedEventsQueryParams, Depends()],
) -> EventListResponse:
    return service.list_created_events(user_id, params)

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Response, UploadFile, status

from app.api.dependencies import CurrentUserId, EventServiceDep, RegistrationServiceDep
from app.schemas.event import (
    EventCreateRequest,
    EventListQueryParams,
    EventListResponse,
    EventPhotoMetaResponse,
    EventResponse,
    EventUpdateRequest,
    ParticipantListResponse,
    ParticipantQueryParams,
    RegistrationResponse,
)


router = APIRouter(prefix="/events", tags=["events"])


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def create_event(
    payload: EventCreateRequest,
    current_user_id: CurrentUserId,
    service: EventServiceDep,
) -> EventResponse:
    return service.create_event(current_user_id, payload)


@router.patch("/{event_id}", response_model=EventResponse)
def update_event(
    event_id: UUID,
    payload: EventUpdateRequest,
    current_user_id: CurrentUserId,
    service: EventServiceDep,
) -> EventResponse:
    return service.update_event(event_id, current_user_id, payload)


@router.post("/{event_id}/cancel", response_model=EventResponse)
def cancel_event(
    event_id: UUID,
    current_user_id: CurrentUserId,
    service: EventServiceDep,
) -> EventResponse:
    return service.cancel_event(event_id, current_user_id)


@router.post("/{event_id}/complete", response_model=EventResponse)
def complete_event(
    event_id: UUID,
    current_user_id: CurrentUserId,
    service: EventServiceDep,
) -> EventResponse:
    return service.complete_event(event_id, current_user_id)


@router.get("", response_model=EventListResponse)
def list_events(
    service: EventServiceDep,
    params: Annotated[EventListQueryParams, Depends()],
) -> EventListResponse:
    return service.list_events(params)


@router.get("/{event_id}", response_model=EventResponse)
def get_event(
    event_id: UUID,
    service: EventServiceDep,
) -> EventResponse:
    return service.get_event(event_id)


@router.post("/{event_id}/photo", response_model=EventPhotoMetaResponse)
async def upload_event_photo(
    event_id: UUID,
    current_user_id: CurrentUserId,
    service: EventServiceDep,
    photo: UploadFile = File(...),
) -> EventPhotoMetaResponse:
    photo_bytes = await photo.read()
    updated_event = service.upload_event_photo(
        event_id,
        current_user_id,
        content_type=photo.content_type or "application/octet-stream",
        data=photo_bytes,
    )
    return EventPhotoMetaResponse(
        has_photo=updated_event.has_photo,
        content_type=photo.content_type,
        size_bytes=len(photo_bytes),
    )


@router.get("/{event_id}/photo")
def get_event_photo(
    event_id: UUID,
    service: EventServiceDep,
) -> Response:
    content_type, photo_data = service.get_event_photo(event_id)
    return Response(content=photo_data, media_type=content_type)


@router.post("/{event_id}/registrations", response_model=RegistrationResponse)
def register_for_event(
    event_id: UUID,
    response: Response,
    current_user_id: CurrentUserId,
    service: RegistrationServiceDep,
) -> RegistrationResponse:
    registration, created = service.register_for_event(event_id, current_user_id)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return registration


@router.delete("/{event_id}/registrations/me", status_code=status.HTTP_204_NO_CONTENT)
def cancel_registration(
    event_id: UUID,
    current_user_id: CurrentUserId,
    service: RegistrationServiceDep,
) -> Response:
    service.cancel_registration(event_id, current_user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{event_id}/participants", response_model=ParticipantListResponse)
def get_participants(
    event_id: UUID,
    current_user_id: CurrentUserId,
    service: RegistrationServiceDep,
    params: Annotated[ParticipantQueryParams, Depends()],
) -> ParticipantListResponse:
    return service.list_participants(event_id, current_user_id, params)


@router.post("/{event_id}/participants/{participant_user_id}/check-in", response_model=RegistrationResponse)
def check_in_participant(
    event_id: UUID,
    participant_user_id: UUID,
    current_user_id: CurrentUserId,
    service: RegistrationServiceDep,
) -> RegistrationResponse:
    return service.check_in_participant(event_id, participant_user_id, current_user_id)

from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError, UnprocessableError
from app.core.security import hash_password, verify_password
from app.models import User
from app.repositories import UserRepository
from app.schemas.user import UserLoginRequest, UserRegisterRequest, UserResponse, UserUpdateRequest
from app.services.mappers import to_user_response


class UserService:
    MAX_PHOTO_SIZE_BYTES = 5 * 1024 * 1024

    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)

    def register_user(self, payload: UserRegisterRequest) -> UserResponse:
        normalized_email = str(payload.email).strip().lower()

        try:
            with self.session.begin():
                existing_user = self.users.get_by_email(normalized_email)
                if existing_user is not None:
                    raise ConflictError("Email is already registered", code="email_already_exists")

                user = User(
                    email=normalized_email,
                    password_hash=hash_password(payload.password),
                    full_name=payload.full_name,
                    work_place=payload.work_place,
                    university=payload.university,
                    faculty=payload.faculty,
                    telegram=payload.telegram,
                )
                self.users.add(user)
                self.session.flush()
        except IntegrityError as exc:
            raise ConflictError("Email is already registered", code="email_already_exists") from exc

        return to_user_response(user)

    def authenticate_user(self, payload: UserLoginRequest) -> UserResponse:
        normalized_email = str(payload.login).strip().lower()
        user = self.users.get_by_email(normalized_email)

        if user is None or user.deleted_at is not None or not user.is_active:
            raise UnauthorizedError("Invalid login or password")

        if not verify_password(payload.password, user.password_hash):
            raise UnauthorizedError("Invalid login or password")

        return to_user_response(user)

    def get_user(self, user_id, current_user_id) -> UserResponse:
        if user_id != current_user_id:
            raise ForbiddenError("You can only access your own profile")

        user = self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found")

        return to_user_response(user)

    def update_user(self, user_id, current_user_id, payload: UserUpdateRequest) -> UserResponse:
        if user_id != current_user_id:
            raise ForbiddenError("You can only update your own profile")

        with self.session.begin():
            user = self.users.get_by_id_for_update(user_id)
            if user is None:
                raise NotFoundError("User not found")

            if "full_name" in payload.model_fields_set:
                user.full_name = payload.full_name
            if "work_place" in payload.model_fields_set:
                user.work_place = payload.work_place
            if "university" in payload.model_fields_set:
                user.university = payload.university
            if "faculty" in payload.model_fields_set:
                user.faculty = payload.faculty
            if "telegram" in payload.model_fields_set:
                user.telegram = payload.telegram

            self.session.flush()

        return to_user_response(user)

    def upload_user_photo(
        self,
        user_id: UUID,
        current_user_id: UUID,
        *,
        content_type: str,
        data: bytes,
    ) -> UserResponse:
        if user_id != current_user_id:
            raise ForbiddenError("You can only update your own profile")
        if not data:
            raise UnprocessableError("Photo file is empty")
        if len(data) > self.MAX_PHOTO_SIZE_BYTES:
            raise UnprocessableError("Photo size must be <= 5MB")
        if not content_type.startswith("image/"):
            raise UnprocessableError("Only image files are allowed")

        with self.session.begin():
            user = self.users.get_by_id_for_update(user_id)
            if user is None:
                raise NotFoundError("User not found")

            user.photo_data = data
            user.photo_content_type = content_type
            user.photo_size_bytes = len(data)
            self.session.flush()

        return self.get_user(user_id, current_user_id)

    def get_user_photo(
        self,
        user_id: UUID,
        current_user_id: UUID | None = None,
    ) -> tuple[str, bytes]:
        _ = current_user_id

        user = self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found")
        if user.photo_data is None or user.photo_content_type is None:
            raise NotFoundError("User photo not found")
        return user.photo_content_type, bytes(user.photo_data)

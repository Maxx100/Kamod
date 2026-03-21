from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import hash_password, verify_password
from app.models import User
from app.repositories import UserRepository
from app.schemas.user import UserLoginRequest, UserRegisterRequest, UserResponse, UserUpdateRequest
from app.services.mappers import to_user_response


class UserService:
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
            if "university" in payload.model_fields_set:
                user.university = payload.university
            if "faculty" in payload.model_fields_set:
                user.faculty = payload.faculty
            if "telegram" in payload.model_fields_set:
                user.telegram = payload.telegram

            self.session.flush()

        return to_user_response(user)

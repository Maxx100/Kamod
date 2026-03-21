from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.security import hash_password
from app.models import User
from app.repositories import UserRepository
from app.schemas.user import UserRegisterRequest, UserResponse
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

    def get_user(self, user_id, current_user_id) -> UserResponse:
        if user_id != current_user_id:
            raise ForbiddenError("You can only access your own profile")

        user = self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found")

        return to_user_response(user)

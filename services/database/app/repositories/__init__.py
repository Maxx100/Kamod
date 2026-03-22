from app.repositories.event import EventRepository
from app.repositories.payment import PaymentRepository
from app.repositories.registration import RegistrationRepository
from app.repositories.tag import TagRepository
from app.repositories.telegram import TelegramAttendanceAnswerRepository, TelegramJobRepository, TelegramSettingsRepository
from app.repositories.user import UserRepository

__all__ = [
    "EventRepository",
    "PaymentRepository",
    "RegistrationRepository",
    "TagRepository",
    "TelegramAttendanceAnswerRepository",
    "TelegramJobRepository",
    "TelegramSettingsRepository",
    "UserRepository",
]

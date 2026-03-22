from enum import Enum


class EventFormat(str, Enum):
    OFFLINE = "offline"
    ONLINE = "online"


class EventStatus(str, Enum):
    PUBLISHED = "published"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class RegistrationStatus(str, Enum):
    REGISTERED = "registered"
    CANCELLED = "cancelled"


class TelegramJobKind(str, Enum):
    REMINDER_24H = "reminder_24h"
    REMINDER_1H = "reminder_1h"
    ATTENDANCE_ASK_24H = "attendance_ask_24h"


class TelegramJobStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AttendanceAnswer(str, Enum):
    YES = "yes"
    NO = "no"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


def enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]

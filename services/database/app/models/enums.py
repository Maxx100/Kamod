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


def enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]

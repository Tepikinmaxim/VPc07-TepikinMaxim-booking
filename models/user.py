from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BLOCKED = "blocked"


class UserRole(str, Enum):
    CUSTOMER = "customer"
    ADMIN = "admin"


@dataclass
class User:
    """Клиент кафе, который может создавать бронирования столиков."""

    full_name: str = field(metadata={"max_length": 150})
    phone: str = field(metadata={"max_length": 32, "unique": True})
    email: str | None = field(
        default=None,
        metadata={"max_length": 254, "unique": True},
    )
    status: UserStatus = field(
        default=UserStatus.ACTIVE,
        metadata={"max_length": 16},
    )
    role: UserRole = field(
        default=UserRole.CUSTOMER,
        metadata={"max_length": 16},
    )
    id: int | None = None
    created_at: datetime | None = field(
        default=None,
        metadata={"nullable": False, "db_default": "CURRENT_TIMESTAMP"},
    )
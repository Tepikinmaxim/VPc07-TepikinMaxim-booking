from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class BookingStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


@dataclass
class Booking:
    """Бронирование конкретного стола конкретным пользователем."""

    user_id: int = field(metadata={"references": ("users", "id")})
    table_id: int = field(metadata={"references": ("tables", "id")})
    reservation_at: datetime
    guests_count: int = field(metadata={"sql_type": "SMALLINT"})
    status: BookingStatus = field(
        default=BookingStatus.PENDING,
        metadata={"max_length": 16},
    )
    id: int | None = None
    created_at: datetime | None = field(
        default=None,
        metadata={"nullable": False, "db_default": "CURRENT_TIMESTAMP"},
    )
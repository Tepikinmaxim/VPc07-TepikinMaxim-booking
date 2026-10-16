from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TableStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    MAINTENANCE = "maintenance"


class TableLocation(str, Enum):
    MAIN_HALL = "main_hall"
    WINDOW = "window"
    TERRACE = "terrace"
    PRIVATE_ROOM = "private_room"


@dataclass
class Table:
    """Один конкретный стол ресторана, доступный для бронирования."""

    table_number: int = field(metadata={"sql_type": "INTEGER", "unique": True})
    seats: int = field(metadata={"sql_type": "SMALLINT"})
    location: TableLocation = field(metadata={"max_length": 16})
    status: TableStatus = field(
        default=TableStatus.AVAILABLE,
        metadata={"max_length": 16},
    )
    id: int | None = None
    created_at: datetime | None = field(
        default=None,
        metadata={"nullable": False, "db_default": "CURRENT_TIMESTAMP"},
    )
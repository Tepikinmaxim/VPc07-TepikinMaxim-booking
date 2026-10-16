from datetime import datetime
from typing import Any

from models.booking import Booking, BookingStatus
from models.tables import Table
from models.user import User
from postgres_driver import BOOKING_DURATION, PostgresSQLDriver


def _create(instance: Any) -> int:
    with PostgresSQLDriver() as db:
        return db.insert_model(instance)


def _read(model: type[Any], record_id: int) -> dict[str, Any] | None:
    with PostgresSQLDriver() as db:
        return db.get_model(model, record_id)


def _read_all(model: type[Any]) -> list[dict[str, Any]]:
    with PostgresSQLDriver() as db:
        return db.get_models(model)


def _update(model: type[Any], record_id: int, changes: dict[str, Any]) -> bool:
    with PostgresSQLDriver() as db:
        return db.update_model(model, record_id, changes)


def _delete(model: type[Any], record_id: int) -> bool:
    with PostgresSQLDriver() as db:
        return db.delete_model(model, record_id)


def create_tables() -> None:
    """Создаёт отсутствующие таблицы, не изменяя уже существующие."""
    with PostgresSQLDriver() as db:
        db.create_table_from_model(User)
        db.create_table_from_model(Table)
        db.create_table_from_model(Booking)


def create_user(user: User) -> int:
    return _create(user)


def get_user(user_id: int) -> dict[str, Any] | None:
    return _read(User, user_id)


def get_users() -> list[dict[str, Any]]:
    return _read_all(User)


def update_user(user_id: int, changes: dict[str, Any]) -> bool:
    return _update(User, user_id, changes)


def delete_user(user_id: int) -> bool:
    return _delete(User, user_id)


def create_table(table: Table) -> int:
    return _create(table)


def get_table(table_id: int) -> dict[str, Any] | None:
    return _read(Table, table_id)


def get_tables() -> list[dict[str, Any]]:
    return _read_all(Table)


def update_table(table_id: int, changes: dict[str, Any]) -> bool:
    return _update(Table, table_id, changes)


def delete_table(table_id: int) -> bool:
    return _delete(Table, table_id)


def create_booking(booking: Booking) -> int:
    with PostgresSQLDriver() as db:
        with db.transaction():
            if not db.check_table_availability(
                booking.table_id,
                booking.reservation_at,
            ):
                raise ValueError(
                    f"Стол {booking.table_id} уже занят на выбранное время "
                    f"(интервал бронирования — {BOOKING_DURATION})."
                )
            return db.insert_model(booking)


def check_table_availability(
    table_id: int,
    reservation_at: datetime,
    exclude_booking_id: int | None = None,
) -> bool:
    with PostgresSQLDriver() as db:
        return db.check_table_availability(
            table_id,
            reservation_at,
            exclude_booking_id=exclude_booking_id,
        )


def get_booking(booking_id: int) -> dict[str, Any] | None:
    return _read(Booking, booking_id)


def get_bookings() -> list[dict[str, Any]]:
    return _read_all(Booking)


def update_booking(booking_id: int, changes: dict[str, Any]) -> bool:
    with PostgresSQLDriver() as db:
        with db.transaction():
            current_booking = db.get_model(Booking, booking_id)
            if current_booking is None:
                return False

            updated_table_id = changes.get("table_id", current_booking["table_id"])
            updated_reservation_at = changes.get(
                "reservation_at",
                current_booking["reservation_at"],
            )
            updated_status = changes.get("status", current_booking["status"])
            if isinstance(updated_status, BookingStatus):
                updated_status = updated_status.value

            if updated_status in {
                BookingStatus.PENDING.value,
                BookingStatus.CONFIRMED.value,
            } and not db.check_table_availability(
                updated_table_id,
                updated_reservation_at,
                exclude_booking_id=booking_id,
            ):
                raise ValueError(
                    f"Стол {updated_table_id} уже занят на выбранное время "
                    f"(интервал бронирования — {BOOKING_DURATION})."
                )

            return db.update_model(Booking, booking_id, changes)


def delete_booking(booking_id: int) -> bool:
    return _delete(Booking, booking_id)


if __name__ == "__main__":
    create_tables()
    print("Таблицы users, tables и bookings созданы или уже существуют.")
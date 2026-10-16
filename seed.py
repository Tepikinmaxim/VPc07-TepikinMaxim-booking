from datetime import datetime, timedelta, timezone
from itertools import count
from secrets import randbelow

from backend import create_tables
from models.booking import Booking
from models.tables import Table, TableLocation
from models.user import User
from postgres_driver import PostgresSQLDriver


USER_NAMES = (
    "Анна Иванова",
    "Иван Петров",
    "Мария Смирнова",
    "Алексей Соколов",
    "Елена Кузнецова",
)
TABLE_CAPACITIES = (2, 4, 6, 4, 2, 6, 4, 2, 6, 4)


def _next_user_contact(
    used_phones: set[str],
    used_emails: set[str],
    sequence: count,
) -> tuple[str, str]:
    for number in sequence:
        phone = f"+7-900-000-{number:06d}"
        email = f"seed{number}@booking.local"
        if phone not in used_phones and email not in used_emails:
            used_phones.add(phone)
            used_emails.add(email)
            return phone, email
    raise RuntimeError("Не удалось подобрать уникальные контакты пользователя.")


def seed_database() -> tuple[int, int, int]:
    """Добавляет пять клиентов, десять столов и по 2-4 бронирования каждому."""
    create_tables()

    with PostgresSQLDriver() as db:
        existing_users = db.get_models(User)
        existing_tables = db.get_models(Table)

        used_phones = {
            str(user["phone"])
            for user in existing_users
            if user.get("phone") is not None
        }
        used_emails = {
            str(user["email"])
            for user in existing_users
            if user.get("email") is not None
        }
        contact_sequence = count(1)

        used_table_numbers = {
            int(table["table_number"])
            for table in existing_tables
            if table.get("table_number") is not None
        }
        table_number_sequence = count(1)

        with db.transaction():
            user_ids: list[int] = []
            for full_name in USER_NAMES:
                phone, email = _next_user_contact(
                    used_phones,
                    used_emails,
                    contact_sequence,
                )
                user_ids.append(
                    db.insert_model(
                        User(
                            full_name=full_name,
                            phone=phone,
                            email=email,
                        )
                    )
                )

            table_ids_and_capacities: list[tuple[int, int]] = []
            locations = tuple(TableLocation)
            for index, seats in enumerate(TABLE_CAPACITIES):
                table_number = next(table_number_sequence)
                while table_number in used_table_numbers:
                    table_number = next(table_number_sequence)
                used_table_numbers.add(table_number)

                table_id = db.insert_model(
                    Table(
                        table_number=table_number,
                        seats=seats,
                        location=locations[index % len(locations)],
                    )
                )
                table_ids_and_capacities.append((table_id, seats))

            booking_count = 0
            now = datetime.now(timezone.utc)
            for user_index, user_id in enumerate(user_ids):
                available_tables = [
                    table for table in table_ids_and_capacities if table[1] >= 1
                ]
                requested_bookings = 2 + randbelow(3)
                selected_tables = [
                    available_tables.pop(randbelow(len(available_tables)))
                    for _ in range(requested_bookings)
                ]

                for booking_index, (table_id, seats) in enumerate(selected_tables):
                    db.insert_model(
                        Booking(
                            user_id=user_id,
                            table_id=table_id,
                            reservation_at=now
                            + timedelta(days=user_index + 1, hours=booking_index),
                            guests_count=1 + randbelow(seats),
                        )
                    )
                    booking_count += 1

    return len(user_ids), len(table_ids_and_capacities), booking_count


if __name__ == "__main__":
    users_added, tables_added, bookings_added = seed_database()
    print(
        f"Добавлены пользователи: {users_added}, столы: {tables_added}, "
        f"бронирования: {bookings_added}."
    )
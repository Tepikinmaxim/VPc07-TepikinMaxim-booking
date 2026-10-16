# Инструкция: создание таблиц и добавление данных

В проекте схема PostgreSQL создаётся на основе dataclass-моделей в `models/`.
Для работы с базой используется `PostgresDriver` из `postgres_driver.py`.

## Подготовка

1. Установите зависимости проекта:

   ```bash
   python -m pip install -r requirements.txt
   ```

2. Настройте подключение к PostgreSQL в `.env` в корне проекта:

   ```dotenv
   PGHOST=localhost
   PGPORT=5432
   PGDATABASE=booking
   PGUSER=postgres
   PGPASSWORD=ваш_пароль
   ```

   Не добавляйте настоящий пароль в Git.

3. Запускайте примеры из корневой папки проекта, чтобы импорты `models.*`
   разрешались корректно.

## Графический интерфейс

Для управления пользователями, столами и бронированиями в Tkinter запустите
приложение из корневой папки:

```bash
.venv/bin/python main.py
```

В каждой вкладке доступны создание, чтение по ID, просмотр списка, обновление
и удаление записей. Кнопка вверху окна создаёт отсутствующие таблицы.

## Создание таблиц из моделей

Метод `create_table()` принимает **класс** dataclass-модели. Сначала создаются
таблицы, на которые ссылается бронирование, затем сама таблица бронирований:

```python
from models.booking import Booking
from models.tables import Table
from models.user import User
from postgres_driver import PostgresDriver

with PostgresDriver() as db:
    db.create_table(User)
    db.create_table(Table)
    db.create_table(Booking)
```

Таблицы называются по имени класса во множественном числе: `User` создаёт
`users`, `Table` — `tables`, `Booking` — `bookings`. Метод выполняет
`CREATE TABLE IF NOT EXISTS`: он создаёт отсутствующую таблицу, но не изменяет
уже существующую схему. После изменения модели существующую таблицу нужно
обновить миграцией или вручную.

Внешние ключи в `Booking` ссылаются на `users.id` и `tables.id`. Если создать
`bookings` раньше `users` и `tables`, PostgreSQL не сможет создать эти ссылки.

В приложении эту последовательность можно запустить через backend-функцию:

```python
from backend import create_tables

create_tables()
```

Функция открывает драйвер через контекстный менеджер, создаёт `users`,
`tables` и `bookings`, затем закрывает соединение. Сам вызов требует доступной
конфигурации PostgreSQL в `.env`. Для запуска непосредственно из терминала
выполните из корневой папки:

```bash
python backend.py
```

## Добавление клиента

`insert_model()` принимает **экземпляр** модели и возвращает ID, присвоенный
PostgreSQL. Поля `id` и `created_at` со значениями `None` пропускаются, чтобы
сработали значения базы данных:

```python
from models.user import User
from postgres_driver import PostgresDriver

guest = User(
    full_name="Анна Иванова",
    phone="+7 900 123-45-67",
    email="anna@example.com",
)

with PostgresDriver() as db:
    db.create_table(User)
    guest_id = db.insert_model(guest)
    print(f"ID клиента: {guest_id}")
```

Поле `email` необязательное. Телефон уникален, поэтому повторная вставка того
же телефона завершится ошибкой ограничения PostgreSQL.

## CRUD-функции backend

В `backend.py` есть функции создания, чтения, обновления и удаления для каждой
модели. Перед их использованием создайте таблицы вызовом `create_tables()`.
Функции открытия базы данных выполняют автоматически и закрывают соединение
после каждой операции.

```python
from backend import (
    create_booking,
    create_table,
    create_user,
    delete_booking,
    delete_table,
    delete_user,
    get_booking,
    get_bookings,
    get_table,
    get_tables,
    get_user,
    get_users,
    update_booking,
    update_table,
    update_user,
)
```

Функции `create_user(user)`, `create_table(table)` и `create_booking(booking)`
возвращают ID новой строки. Функции `get_user(id)`, `get_table(id)` и
`get_booking(id)` возвращают словарь полей либо `None`, если запись не найдена.
Функции `get_users()`, `get_tables()` и `get_bookings()` возвращают список
словарей.

Для изменений передавайте словарь с именами полей модели. Нельзя обновлять
`id` и `created_at`. Операции `update_*` и `delete_*` возвращают `True`, если
строка найдена и изменена/удалена, иначе `False`.

```python
from backend import get_user, get_users, update_user, delete_user

print(get_users())
print(get_user(1))

updated = update_user(1, {"phone": "+7 900 000-00-00"})
deleted = delete_user(1)
```

Так же работают `get_tables()` / `get_table(id)`, `update_table(id, changes)`,
`delete_table(id)` и соответствующие функции для бронирований. Для enum-полей
при обновлении можно передавать элемент перечисления, например
`{"status": BookingStatus.CONFIRMED}`. Ошибки ограничений и соединения
передаются вызывающему коду; например, удаление пользователя с бронированиями
может быть запрещено внешним ключом.

Перед созданием или переносом бронирования backend вызывает
`check_table_availability(table_id, reservation_at, exclude_booking_id=None)`.
Оно возвращает `True`, если стол существует и нет пересекающегося активного
бронирования в течение двухчасового интервала. Границы интервалов считаются
полуоткрытыми: бронирование, начинающееся ровно в момент окончания предыдущего,
допустимо. Для бронирования, которое обновляется, его ID исключается из поиска
конфликтов. В GUI доступность также можно проверить кнопкой на вкладке
«Бронирования»; успешная проверка не резервирует время сама по себе, поэтому
создавайте бронь сразу после проверки.

## Добавление стола и бронирования

Сначала создайте таблицы, затем сохраните клиента и стол. Их возвращённые ID
передаются в `Booking` как внешние ключи:

```python
from datetime import datetime, timedelta, timezone

from models.booking import Booking, BookingStatus
from models.tables import Table, TableLocation
from models.user import User
from postgres_driver import PostgresDriver

with PostgresDriver() as db:
    db.create_table(User)
    db.create_table(Table)
    db.create_table(Booking)

    guest_id = db.insert_model(
        User(
            full_name="Анна Иванова",
            phone="+7 900 123-45-67",
            email="anna@example.com",
        )
    )
    table_id = db.insert_model(
        Table(
            table_number=12,
            seats=4,
            location=TableLocation.WINDOW,
        )
    )
    booking_id = db.insert_model(
        Booking(
            user_id=guest_id,
            table_id=table_id,
            reservation_at=datetime.now(timezone.utc) + timedelta(days=1),
            guests_count=3,
            status=BookingStatus.PENDING,
        )
    )

    print(f"ID бронирования: {booking_id}")
```

Для `reservation_at` используется время с часовым поясом. Статус бронирования
по умолчанию — `PENDING`, поэтому его можно не передавать; в примере он указан
явно для наглядности.

## Транзакции и ошибки

Операции `create_table()` и `insert_model()` выполняются в транзакциях. Их
можно объединить во внешнюю транзакцию, чтобы при ошибке отменить все связанные
изменения:

```python
from datetime import datetime, timedelta, timezone

from models.booking import Booking
from models.tables import Table, TableLocation
from models.user import User
from postgres_driver import PostgresDriver

with PostgresDriver() as db:
    db.create_table(User)
    db.create_table(Table)
    db.create_table(Booking)

    with db.transaction():
        guest_id = db.insert_model(
            User(full_name="Иван Петров", phone="+7 900 111-22-33")
        )
        table_id = db.insert_model(
            Table(table_number=5, seats=2, location=TableLocation.TERRACE)
        )
        db.insert_model(
            Booking(
                user_id=guest_id,
                table_id=table_id,
                reservation_at=datetime.now(timezone.utc) + timedelta(days=2),
                guests_count=2,
            )
        )
```

Ошибки подключения, типов данных, уникальности и внешних ключей не скрываются:
проверьте конфигурацию `.env`, значения модели и порядок создания связанных
записей.

## Преобразование полей

`create_table()` использует аннотации типов и метаданные dataclass:

- `str` преобразуется в `TEXT` или `VARCHAR(n)` при `max_length`;
- `int` по умолчанию преобразуется в `BIGINT`, либо в `SMALLINT`/`INTEGER`/
  `BIGINT` из метаданных `sql_type`;
- `datetime` преобразуется в `TIMESTAMPTZ`;
- строковые `Enum` получают `CHECK` со значениями перечисления;
- `unique` добавляет ограничение уникальности;
- `references` задаёт внешний ключ;
- `db_default="CURRENT_TIMESTAMP"` задаёт серверное значение по умолчанию;
- поле `id` создаётся как identity primary key.

Необязательность типа (`T | None`) по умолчанию делает колонку nullable.
Метаданные `nullable` могут переопределить это правило, например для
`created_at`, которое допускает `None` в объекте до сохранения, но в таблице
обязательное и заполняется базой.

# Мини-система бронирования столиков в кафе

Проект предназначен для создания системы, в которой гости смогут бронировать
столики в кафе. Включает модели клиентов, столов и бронирований, backend для
работы с PostgreSQL и графический интерфейс на Tkinter.

## Запуск графического интерфейса

Настройте подключение к PostgreSQL в `.env`, установите зависимости и запустите
из корневой папки проекта:

```bash
.venv/bin/python main.py
```

Вкладки позволяют создавать, читать, обновлять и удалять пользователей, столы
и бронирования. Список записей обновляется по кнопке «Обновить список»; запись
можно загрузить по ID или выбрать в таблице. Кнопка «Создать таблицы БД»
создаёт недостающие таблицы. Для бронирования указывайте ID существующих
пользователя и стола, а дату — в ISO 8601 с часовым поясом, например
`2026-10-20T19:00:00+03:00`.
На вкладке бронирований доступна проверка доступности стола. Каждое бронирование
занимает стол на два часа; при создании или изменении брони пересекающееся
бронирование того же стола отклоняется.

Кнопка **«Заполнить БД тестовыми данными»** добавляет тестовый набор после
подтверждения и автоматически обновляет списки на вкладках. Она добавляет
пять пользователей, десять столов и от двух до четырёх бронирований для
каждого; повторный запуск добавляет новый набор.

Также тестовые данные можно добавить из терминала:

```bash
.venv/bin/python seed.py
```

Скрипт добавляет пять пользователей, десять столов и от двух до четырёх
бронирований на пользователя. В бронированиях одного пользователя используются
разные столы. Новые номера столов и контакты подбираются с учётом уже
существующих записей; каждое выполнение добавляет новый тестовый набор.

## Модель клиента

Класс `User` находится в `models/user.py`. Он описывает клиента, который может
создавать бронирования.

| Поле | Тип Python | Поле будущей таблицы | Назначение |
| --- | --- | --- | --- |
| `id` | `int \| None` | `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY` | Уникальный идентификатор; до сохранения записи не задан |
| `full_name` | `str` | `full_name VARCHAR(150) NOT NULL` | Имя клиента для оформления и отображения бронирования |
| `phone` | `str` | `phone VARCHAR(32) NOT NULL UNIQUE` | Контактный телефон; строка позволяет хранить `+` и форматирование |
| `email` | `str \| None` | `email VARCHAR(254) UNIQUE` | Необязательный адрес электронной почты |
| `status` | `UserStatus` | `status VARCHAR(16) NOT NULL DEFAULT 'active'` | Состояние учётной записи: `active`, `inactive` или `blocked` |
| `role` | `UserRole` | `role VARCHAR(16) NOT NULL DEFAULT 'customer'` | Права пользователя: `customer` или `admin` |
| `created_at` | `datetime \| None` | `created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP` | Дата и время регистрации клиента; обычно устанавливаются базой данных |

Допустимые значения `status` и `role` ограничены перечислениями `UserStatus` и
`UserRole` в `models/user.py`. Значения по умолчанию — активный клиент. На уровне
будущей таблицы их рекомендуется дополнительно ограничить через `CHECK`:
`status IN ('active', 'inactive', 'blocked')` и `role IN ('customer', 'admin')`.

Пример создания объекта до записи в базу данных:

```python
from models.user import User, UserRole, UserStatus

guest = User(
    full_name="Анна Иванова",
    phone="+7 900 123-45-67",
    email="anna@example.com",
    status=UserStatus.ACTIVE,
    role=UserRole.CUSTOMER,
    id=None,
    created_at=None,
)
```

Чтобы создать администратора или неактивную учётную запись, укажите
соответствующие значения перечислений:

```python
from models.user import User, UserRole, UserStatus

staff = User(
    full_name="Администратор кафе",
    phone="+7 900 555-00-00",
    role=UserRole.ADMIN,
    status=UserStatus.ACTIVE,
)
```

`id` и `created_at` остаются `None`, пока база данных не создаст и не вернёт
соответствующие значения. Телефон выбран обязательным контактом для уточнения
деталей бронирования; электронная почта не обязательна. Телефон и email должны
быть уникальны, если указаны, чтобы клиент не дублировался в системе.

## Модель стола

Класс `Table` находится в `models/tables.py` и описывает один конкретный стол
ресторана.

| Поле | Тип Python | Поле будущей таблицы | Назначение |
| --- | --- | --- | --- |
| `id` | `int \| None` | `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY` | Уникальный идентификатор стола |
| `table_number` | `int` | `table_number INT NOT NULL UNIQUE` | Номер стола в ресторане |
| `seats` | `int` | `seats SMALLINT NOT NULL` | Вместимость стола в местах |
| `location` | `TableLocation` | `location VARCHAR(16) NOT NULL` | Зона ресторана: `main_hall`, `window`, `terrace` или `private_room` |
| `status` | `TableStatus` | `status VARCHAR(16) NOT NULL DEFAULT 'available'` | Состояние: `available`, `unavailable` или `maintenance` |
| `created_at` | `datetime \| None` | `created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP` | Дата и время добавления стола |

Пример объекта до записи в базу данных:

```python
from models.tables import Table, TableLocation, TableStatus

table = Table(
    table_number=12,
    seats=4,
    location=TableLocation.WINDOW,
    status=TableStatus.AVAILABLE,
    id=None,
    created_at=None,
)
```

Статус описывает состояние самого стола. Занятость на конкретное время будет
определяться записями бронирований, а не статусом стола.

## Модель бронирования

Класс `Booking` находится в `models/booking.py` и описывает одно бронирование.
Связи с пользователем и столом хранятся как `user_id` и `table_id` — внешние
ключи на `users.id` и `tables.id`.

| Поле | Тип Python | Поле будущей таблицы | Назначение |
| --- | --- | --- | --- |
| `id` | `int \| None` | `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY` | Уникальный идентификатор бронирования |
| `user_id` | `int` | `user_id BIGINT NOT NULL REFERENCES users(id)` | Пользователь, создавший бронирование |
| `table_id` | `int` | `table_id BIGINT NOT NULL REFERENCES tables(id)` | Забронированный стол |
| `reservation_at` | `datetime` | `reservation_at TIMESTAMPTZ NOT NULL` | Дата и время бронирования |
| `guests_count` | `int` | `guests_count SMALLINT NOT NULL CHECK (guests_count > 0)` | Количество гостей |
| `status` | `BookingStatus` | `status VARCHAR(16) NOT NULL DEFAULT 'pending'` | Состояние: `pending`, `confirmed`, `cancelled` или `completed` |
| `created_at` | `datetime \| None` | `created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP` | Дата и время создания записи |

Допустимые состояния задаются перечислением `BookingStatus`. Новое
бронирование по умолчанию ожидает подтверждения. В будущей таблице рекомендуется
ограничить статус проверкой `CHECK` на допустимые значения.

Пример создания объекта до записи в базу данных:

```python
from datetime import datetime, timezone

from models.booking import Booking, BookingStatus

booking = Booking(
    user_id=1,
    table_id=12,
    reservation_at=datetime(2026, 10, 20, 19, 0, tzinfo=timezone.utc),
    guests_count=4,
    status=BookingStatus.PENDING,
    id=None,
    created_at=None,
)
```

Один пользователь и один стол могут участвовать во многих бронированиях в
разное время. Backend проверяет двухчасовые интервалы пересечения для
бронирований в состояниях `pending` и `confirmed`; отменённые и завершённые
записи не блокируют время.

## Текущее состояние

`PostgresDriver.create_table(Model)` создаёт таблицу по dataclass-модели,
если таблица ещё не существует. Передайте класс, а не экземпляр; для связанной
модели сначала создайте таблицы, на которые ссылаются внешние ключи:

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

Имя таблицы по умолчанию образуется добавлением `s` к имени класса (`User` →
`users`). Типы Python преобразуются в типы PostgreSQL; для пользовательских
полей dataclass поддерживаются метаданные `max_length`, `sql_type`, `unique`,
`references`, `nullable` и `db_default`. Например, `created_at` получает
`CURRENT_TIMESTAMP`, а enum-поля ограничиваются допустимыми значениями
перечисления. `create_table` не меняет уже существующую таблицу. Старый метод
`create_tables()` с учебной схемой удалён.

Подробная инструкция по созданию таблиц и добавлению записей находится в
[DATABASE_GUIDE.md](./DATABASE_GUIDE.md).

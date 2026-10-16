import getpass
import os
from contextlib import closing, contextmanager
from dataclasses import MISSING, fields, is_dataclass
from datetime import datetime, timedelta
from enum import Enum
from types import UnionType
from typing import Any, Iterator, Union, get_args, get_origin, get_type_hints

import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv
from psycopg2.extensions import connection

load_dotenv()

BOOKING_DURATION = timedelta(hours=2)


class PostgresDriver:
    def __init__(self) -> None:
        password = os.getenv("PGPASSWORD") or getpass.getpass("PostgreSQL password: ")
        self._connection: connection = psycopg2.connect(
            host=os.getenv("PGHOST", "localhost"),
            port=int(os.getenv("PGPORT", "5432")),
            dbname=os.getenv("PGDATABASE", "test"),
            user=os.getenv("PGUSER", "postgres"),
            password=password,
            connect_timeout=5,
        )
        self._transaction_depth = 0

    def __enter__(self) -> "PostgresDriver":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def close(self) -> None:
        if not self._connection.closed:
            self._connection.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self._transaction_depth:
            self._transaction_depth += 1
            try:
                yield
            finally:
                self._transaction_depth -= 1
            return

        self._transaction_depth = 1
        try:
            with self._connection:
                yield
        finally:
            self._transaction_depth = 0

    def check_connection(self) -> bool:
        with self.transaction():
            with closing(self._connection.cursor()) as cursor:
                cursor.execute("SELECT 1")
                return cursor.fetchone() == (1,)

    def check_table_availability(
        self,
        table_id: int,
        reservation_at: datetime,
        exclude_booking_id: int | None = None,
    ) -> bool:
        if reservation_at.tzinfo is None or reservation_at.utcoffset() is None:
            raise ValueError("Время бронирования должно содержать часовой пояс.")
        if table_id <= 0:
            raise ValueError("ID стола должен быть больше нуля.")

        reservation_end = reservation_at + BOOKING_DURATION
        with self.transaction():
            with closing(self._connection.cursor()) as cursor:
                cursor.execute(
                    "SELECT id FROM tables WHERE id = %s FOR UPDATE",
                    (table_id,),
                )
                if cursor.fetchone() is None:
                    return False

                query = """
                    SELECT EXISTS (
                        SELECT 1
                        FROM bookings
                        WHERE table_id = %s
                          AND status IN (%s, %s)
                          AND reservation_at < %s
                          AND reservation_at + %s > %s
                """
                params: tuple[Any, ...] = (
                    table_id,
                    "pending",
                    "confirmed",
                    reservation_end,
                    BOOKING_DURATION,
                    reservation_at,
                )
                if exclude_booking_id is not None:
                    query += " AND id <> %s"
                    params += (exclude_booking_id,)
                query += ")"
                cursor.execute(query, params)
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("Не удалось проверить доступность стола.")
                return not row[0]

    def create_table(self, model: type[Any]) -> None:
        if not isinstance(model, type) or not is_dataclass(model):
            raise TypeError("Для создания таблицы требуется класс-модель dataclass.")

        table_name = getattr(model, "__tablename__", f"{model.__name__.lower()}s")
        if not isinstance(table_name, str) or not table_name.isidentifier():
            raise ValueError(f"Некорректное имя таблицы: {table_name!r}")

        type_hints = get_type_hints(model)
        model_fields = fields(model)
        if not model_fields:
            raise ValueError("Для создания таблицы модель должна содержать поля.")
        columns: list[sql.Composed | sql.SQL] = []

        for model_field in model_fields:
            annotation = type_hints.get(model_field.name)
            if annotation is None:
                raise TypeError(
                    f"Поле {model_field.name!r} модели {model.__name__} "
                    "должно иметь аннотацию типа."
                )

            is_nullable = False
            origin = get_origin(annotation)
            if origin in (Union, UnionType):
                args = get_args(annotation)
                is_nullable = type(None) in args
                non_null_args = tuple(arg for arg in args if arg is not type(None))
                if len(non_null_args) != 1:
                    raise TypeError(
                        f"Неподдерживаемый тип поля {model_field.name!r}: "
                        f"{annotation!r}"
                    )
                annotation = non_null_args[0]

            if model_field.name == "id":
                column = sql.SQL(
                    "{} BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"
                ).format(sql.Identifier(model_field.name))
            else:
                if isinstance(annotation, type) and issubclass(annotation, Enum):
                    enum_values = [member.value for member in annotation]
                    if not all(isinstance(value, str) for value in enum_values):
                        raise TypeError(
                            f"Enum поля {model_field.name!r} должен содержать строки."
                        )
                    max_length = model_field.metadata.get("max_length", 32)
                    if not isinstance(max_length, int) or max_length < 1:
                        raise ValueError(
                            f"Некорректная длина поля {model_field.name!r}."
                        )
                    sql_type = sql.SQL(f"VARCHAR({max_length})")
                elif annotation is str:
                    max_length = model_field.metadata.get("max_length")
                    if max_length is not None:
                        if not isinstance(max_length, int) or max_length < 1:
                            raise ValueError(
                                f"Некорректная длина поля {model_field.name!r}."
                            )
                        sql_type = sql.SQL(f"VARCHAR({max_length})")
                    else:
                        sql_type = sql.SQL("TEXT")
                    enum_values = []
                elif annotation is int:
                    sql_type_name = model_field.metadata.get("sql_type", "BIGINT")
                    if sql_type_name not in {"SMALLINT", "INTEGER", "BIGINT"}:
                        raise ValueError(
                            f"Некорректный SQL-тип поля {model_field.name!r}."
                        )
                    sql_type = sql.SQL(sql_type_name)
                    enum_values = []
                elif annotation is datetime:
                    sql_type = sql.SQL("TIMESTAMPTZ")
                    enum_values = []
                else:
                    raise TypeError(
                        f"Неподдерживаемый тип поля {model_field.name!r}: "
                        f"{annotation!r}"
                    )

                column = sql.SQL("{} {}").format(
                    sql.Identifier(model_field.name), sql_type
                )
                nullable = model_field.metadata.get("nullable", is_nullable)
                if not nullable:
                    column += sql.SQL(" NOT NULL")

                if enum_values:
                    allowed_values = sql.SQL(", ").join(
                        sql.Literal(value) for value in enum_values
                    )
                    column += sql.SQL(" CHECK ({} IN ({}))").format(
                        sql.Identifier(model_field.name), allowed_values
                    )

                default = model_field.default
                if isinstance(default, Enum):
                    default = default.value
                if default is not MISSING and default is not None:
                    if not isinstance(default, (str, int, float, bool)):
                        raise TypeError(
                            f"Неподдерживаемое значение по умолчанию поля "
                            f"{model_field.name!r}."
                        )
                    column += sql.SQL(" DEFAULT {}").format(sql.Literal(default))

                db_default = model_field.metadata.get("db_default")
                if db_default is not None:
                    if db_default != "CURRENT_TIMESTAMP":
                        raise ValueError(
                            f"Неподдерживаемое значение db_default поля "
                            f"{model_field.name!r}."
                        )
                    column += sql.SQL(" DEFAULT CURRENT_TIMESTAMP")

                if model_field.metadata.get("unique"):
                    column += sql.SQL(" UNIQUE")

                reference = model_field.metadata.get("references")
                if reference is not None:
                    if (
                        not isinstance(reference, tuple)
                        or len(reference) != 2
                        or not all(
                            isinstance(part, str) and part.isidentifier()
                            for part in reference
                        )
                    ):
                        raise ValueError(
                            f"Некорректная ссылка для поля {model_field.name!r}."
                        )
                    referenced_table, referenced_column = reference
                    column += sql.SQL(" REFERENCES {} ({})").format(
                        sql.Identifier(referenced_table),
                        sql.Identifier(referenced_column),
                    )

            columns.append(column)

        query = sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
            sql.Identifier(table_name),
            sql.SQL(", ").join(columns),
        )
        with self.transaction():
            with closing(self._connection.cursor()) as cursor:
                cursor.execute(query)

    def create_table_from_model(self, model: type[Any]) -> None:
        self.create_table(model)

    def insert_model(self, instance: Any) -> int:
        if isinstance(instance, type) or not is_dataclass(instance):
            raise TypeError("Для вставки требуется экземпляр dataclass-модели.")

        model = type(instance)
        table_name = getattr(model, "__tablename__", f"{model.__name__.lower()}s")
        if not isinstance(table_name, str) or not table_name.isidentifier():
            raise ValueError(f"Некорректное имя таблицы: {table_name!r}")

        columns: list[sql.Identifier] = []
        values: list[Any] = []
        for model_field in fields(instance):
            value = getattr(instance, model_field.name)
            if model_field.name == "id" and value is None:
                continue
            if value is None and model_field.metadata.get("db_default") is not None:
                continue
            if isinstance(value, Enum):
                value = value.value
            columns.append(sql.Identifier(model_field.name))
            values.append(value)

        if not columns:
            raise ValueError("Для вставки dataclass-модель должна содержать значения.")

        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in values)
        query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING id").format(
            sql.Identifier(table_name),
            sql.SQL(", ").join(columns),
            placeholders,
        )
        with self.transaction():
            with closing(self._connection.cursor()) as cursor:
                cursor.execute(query, values)
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError(
                        f"Не удалось получить ID созданной записи таблицы "
                        f"{table_name!r}."
                    )
                return row[0]

    def get_model(self, model: type[Any], record_id: int) -> dict[str, Any] | None:
        if not isinstance(model, type) or not is_dataclass(model):
            raise TypeError("Для чтения требуется класс-модель dataclass.")

        table_name = getattr(model, "__tablename__", f"{model.__name__.lower()}s")
        if not isinstance(table_name, str) or not table_name.isidentifier():
            raise ValueError(f"Некорректное имя таблицы: {table_name!r}")

        column_names = [model_field.name for model_field in fields(model)]
        query = sql.SQL("SELECT {} FROM {} WHERE id = %s").format(
            sql.SQL(", ").join(sql.Identifier(name) for name in column_names),
            sql.Identifier(table_name),
        )
        with self.transaction():
            with closing(self._connection.cursor()) as cursor:
                cursor.execute(query, (record_id,))
                row = cursor.fetchone()
                if row is None:
                    return None
                return dict(zip(column_names, row))

    def get_models(self, model: type[Any]) -> list[dict[str, Any]]:
        if not isinstance(model, type) or not is_dataclass(model):
            raise TypeError("Для чтения требуется класс-модель dataclass.")

        table_name = getattr(model, "__tablename__", f"{model.__name__.lower()}s")
        if not isinstance(table_name, str) or not table_name.isidentifier():
            raise ValueError(f"Некорректное имя таблицы: {table_name!r}")

        column_names = [model_field.name for model_field in fields(model)]
        query = sql.SQL("SELECT {} FROM {} ORDER BY id").format(
            sql.SQL(", ").join(sql.Identifier(name) for name in column_names),
            sql.Identifier(table_name),
        )
        with self.transaction():
            with closing(self._connection.cursor()) as cursor:
                cursor.execute(query)
                return [
                    dict(zip(column_names, row))
                    for row in cursor.fetchall()
                ]

    def update_model(
        self,
        model: type[Any],
        record_id: int,
        changes: dict[str, Any],
    ) -> bool:
        if not isinstance(model, type) or not is_dataclass(model):
            raise TypeError("Для обновления требуется класс-модель dataclass.")
        if not changes:
            raise ValueError("Для обновления укажите хотя бы одно поле.")

        model_fields = {model_field.name for model_field in fields(model)}
        forbidden_fields = {"id", "created_at"}
        invalid_fields = changes.keys() - model_fields | changes.keys() & forbidden_fields
        if invalid_fields:
            raise ValueError(
                f"Недопустимые поля для обновления: {', '.join(sorted(invalid_fields))}."
            )

        table_name = getattr(model, "__tablename__", f"{model.__name__.lower()}s")
        if not isinstance(table_name, str) or not table_name.isidentifier():
            raise ValueError(f"Некорректное имя таблицы: {table_name!r}")

        assignments = sql.SQL(", ").join(
            sql.SQL("{} = %s").format(sql.Identifier(name)) for name in changes
        )
        values = [
            value.value if isinstance(value, Enum) else value
            for value in changes.values()
        ]
        query = sql.SQL("UPDATE {} SET {} WHERE id = %s RETURNING id").format(
            sql.Identifier(table_name),
            assignments,
        )
        with self.transaction():
            with closing(self._connection.cursor()) as cursor:
                cursor.execute(query, (*values, record_id))
                return cursor.fetchone() is not None

    def delete_model(self, model: type[Any], record_id: int) -> bool:
        if not isinstance(model, type) or not is_dataclass(model):
            raise TypeError("Для удаления требуется класс-модель dataclass.")

        table_name = getattr(model, "__tablename__", f"{model.__name__.lower()}s")
        if not isinstance(table_name, str) or not table_name.isidentifier():
            raise ValueError(f"Некорректное имя таблицы: {table_name!r}")

        query = sql.SQL("DELETE FROM {} WHERE id = %s RETURNING id").format(
            sql.Identifier(table_name),
        )
        with self.transaction():
            with closing(self._connection.cursor()) as cursor:
                cursor.execute(query, (record_id,))
                return cursor.fetchone() is not None


PostgresSQLDriver = PostgresDriver

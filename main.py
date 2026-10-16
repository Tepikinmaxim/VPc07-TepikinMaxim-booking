from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable

import backend
from models.booking import Booking, BookingStatus
from models.tables import Table, TableLocation, TableStatus
from models.user import User, UserRole, UserStatus
from seed import seed_database


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    kind: str = "text"
    enum_type: type[Enum] | None = None
    optional: bool = False


@dataclass(frozen=True)
class EntitySpec:
    title: str
    model: type[Any]
    fields: tuple[FieldSpec, ...]
    create: Callable[[Any], int]
    read: Callable[[int], dict[str, Any] | None]
    read_all: Callable[[], list[dict[str, Any]]]
    update: Callable[[int, dict[str, Any]], bool]
    delete: Callable[[int], bool]
    check_availability: Callable[[int, datetime, int | None], bool] | None = None
    additional_columns: tuple[tuple[str, str], ...] = ()


ENTITY_SPECS = (
    EntitySpec(
        "Пользователи",
        User,
        (
            FieldSpec("full_name", "Имя"),
            FieldSpec("phone", "Телефон"),
            FieldSpec("email", "Email", optional=True),
            FieldSpec("status", "Статус", "enum", UserStatus),
            FieldSpec("role", "Роль", "enum", UserRole),
        ),
        backend.create_user,
        backend.get_user,
        backend.get_users,
        backend.update_user,
        backend.delete_user,
    ),
    EntitySpec(
        "Столы",
        Table,
        (
            FieldSpec("table_number", "Номер", "int"),
            FieldSpec("seats", "Мест", "int"),
            FieldSpec("location", "Расположение", "enum", TableLocation),
            FieldSpec("status", "Статус", "enum", TableStatus),
        ),
        backend.create_table,
        backend.get_table,
        backend.get_tables,
        backend.update_table,
        backend.delete_table,
    ),
    EntitySpec(
        "Бронирования",
        Booking,
        (
            FieldSpec("user_id", "ID пользователя", "int"),
            FieldSpec("table_id", "ID стола", "int"),
            FieldSpec("reservation_at", "Дата и время (ISO 8601)", "datetime"),
            FieldSpec("guests_count", "Количество гостей", "int"),
            FieldSpec("status", "Статус", "enum", BookingStatus),
        ),
        backend.create_booking,
        backend.get_booking,
        backend.get_bookings,
        backend.update_booking,
        backend.delete_booking,
        backend.check_table_availability,
        (("user_name", "Имя пользователя"),),
    ),
)


class EntityTab(ttk.Frame):
    def __init__(self, master: ttk.Notebook, spec: EntitySpec) -> None:
        super().__init__(master, padding=12)
        self.spec = spec
        self.record_id = tk.StringVar()
        self.inputs: dict[str, ttk.Entry | ttk.Combobox] = {}
        self._build_form()
        self._build_actions()
        self._build_records()

    def _build_form(self) -> None:
        form = ttk.LabelFrame(self, text="Данные записи", padding=10)
        form.pack(fill=tk.X, pady=(0, 10))
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="ID записи").grid(
            row=0, column=0, sticky=tk.W, padx=(0, 10), pady=4
        )
        ttk.Entry(form, textvariable=self.record_id, width=18).grid(
            row=0, column=1, sticky=tk.W, pady=4
        )

        for row, field in enumerate(self.spec.fields, start=1):
            ttk.Label(form, text=field.label).grid(
                row=row, column=0, sticky=tk.W, padx=(0, 10), pady=4
            )
            if field.kind == "enum":
                assert field.enum_type is not None
                values = [member.value for member in field.enum_type]
                widget = ttk.Combobox(
                    form,
                    values=values,
                    state="readonly",
                    width=32,
                )
                default_value = values[0]
                if field.name == "status":
                    default_member = getattr(field.enum_type, "ACTIVE", None)
                    if default_member is None:
                        default_member = getattr(field.enum_type, "AVAILABLE", None)
                    if default_member is None:
                        default_member = getattr(field.enum_type, "PENDING", None)
                    if default_member is not None:
                        default_value = default_member.value
                widget.set(default_value)
            else:
                widget = ttk.Entry(form, width=35)
            widget.grid(row=row, column=1, sticky=tk.EW, pady=4)
            self.inputs[field.name] = widget

    def _build_actions(self) -> None:
        actions = ttk.Frame(self)
        actions.pack(fill=tk.X, pady=(0, 10))
        buttons = (
            ("Создать", self.create_record),
            ("Найти по ID", self.read_record),
            ("Обновить", self.update_record),
            ("Удалить", self.delete_record),
            ("Обновить список", self.refresh_records),
            ("Очистить форму", self.clear_form),
        )
        if self.spec.check_availability is not None:
            buttons = (
                *buttons[:-1],
                ("Проверить доступность", self.check_availability),
                buttons[-1],
            )
        for text, command in buttons:
            ttk.Button(actions, text=text, command=command).pack(
                side=tk.LEFT, padx=(0, 6), pady=2
            )

    def _build_records(self) -> None:
        container = ttk.LabelFrame(self, text="Записи", padding=6)
        container.pack(fill=tk.BOTH, expand=True)
        columns = (
            "id",
            *(field.name for field in self.spec.fields),
            *(name for name, _ in self.spec.additional_columns),
            "created_at",
        )
        self.tree = ttk.Treeview(
            container,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        headings = {"id": "ID", "created_at": "Создано"}
        headings.update({field.name: field.label for field in self.spec.fields})
        headings.update(dict(self.spec.additional_columns))
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=145, minwidth=90, stretch=True)
        vertical = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.tree.yview)
        horizontal = ttk.Scrollbar(
            container,
            orient=tk.HORIZONTAL,
            command=self.tree.xview,
        )
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        vertical.grid(row=0, column=1, sticky=tk.NS)
        horizontal.grid(row=1, column=0, sticky=tk.EW)
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._select_record)

    def _get_input(self, field: FieldSpec) -> Any:
        widget = self.inputs[field.name]
        value = widget.get().strip()
        if not value and field.optional:
            return None
        if not value:
            raise ValueError(f"Заполните поле «{field.label}».")
        if field.kind == "int":
            parsed = int(value)
            if parsed <= 0:
                raise ValueError(f"Поле «{field.label}» должно быть больше нуля.")
            return parsed
        if field.kind == "datetime":
            parsed_datetime = datetime.fromisoformat(value)
            if parsed_datetime.tzinfo is None or parsed_datetime.utcoffset() is None:
                raise ValueError(
                    "Укажите часовой пояс, например "
                    "2026-10-20T19:00:00+03:00."
                )
            return parsed_datetime
        if field.kind == "enum":
            assert field.enum_type is not None
            return field.enum_type(value)
        return value

    def _values(self) -> dict[str, Any]:
        return {field.name: self._get_input(field) for field in self.spec.fields}

    def _id(self) -> int:
        value = self.record_id.get().strip()
        if not value:
            selected = self.tree.selection()
            if selected:
                value = str(self.tree.item(selected[0], "values")[0])
        if not value:
            raise ValueError("Укажите ID записи или выберите её в списке.")
        record_id = int(value)
        if record_id <= 0:
            raise ValueError("ID должен быть больше нуля.")
        return record_id

    def _run(self, action: Callable[[], Any]) -> None:
        try:
            action()
        except (ValueError, TypeError) as error:
            messagebox.showerror("Проверьте данные", str(error), parent=self)
        except Exception as error:
            messagebox.showerror(
                "Ошибка операции",
                f"{type(error).__name__}: {error}",
                parent=self,
            )

    def create_record(self) -> None:
        def create() -> None:
            record = self.spec.model(**self._values())
            record_id = self.spec.create(record)
            self.record_id.set(str(record_id))
            self.refresh_records()
            messagebox.showinfo(
                "Запись создана",
                f"{self.spec.title}: запись с ID {record_id} добавлена.",
                parent=self,
            )

        self._run(create)

    def read_record(self) -> None:
        def read() -> None:
            record_id = self._id()
            record = self.spec.read(record_id)
            if record is None:
                messagebox.showinfo(
                    "Не найдено",
                    f"Запись с ID {record_id} не найдена.",
                    parent=self,
                )
                return
            self._show_record(record)

        self._run(read)

    def update_record(self) -> None:
        def update() -> None:
            record_id = self._id()
            updated = self.spec.update(record_id, self._values())
            if not updated:
                messagebox.showinfo(
                    "Не найдено",
                    f"Запись с ID {record_id} не найдена.",
                    parent=self,
                )
                return
            self.refresh_records()
            messagebox.showinfo("Готово", "Запись обновлена.", parent=self)

        self._run(update)

    def check_availability(self) -> None:
        if self.spec.check_availability is None:
            return

        def check() -> None:
            table_id = self._get_input(
                next(field for field in self.spec.fields if field.name == "table_id")
            )
            reservation_at = self._get_input(
                next(
                    field
                    for field in self.spec.fields
                    if field.name == "reservation_at"
                )
            )
            value = self.record_id.get().strip()
            exclude_booking_id = int(value) if value else None
            available = self.spec.check_availability(
                table_id,
                reservation_at,
                exclude_booking_id,
            )
            if available:
                messagebox.showinfo(
                    "Стол свободен",
                    "Стол доступен для бронирования на выбранные два часа.",
                    parent=self,
                )
            else:
                messagebox.showwarning(
                    "Стол недоступен",
                    "Стол отсутствует или уже забронирован на пересекающееся время.",
                    parent=self,
                )

        self._run(check)

    def delete_record(self) -> None:
        def delete() -> None:
            record_id = self._id()
            if not messagebox.askyesno(
                "Подтверждение удаления",
                f"Удалить запись {record_id}?",
                parent=self,
            ):
                return
            if not self.spec.delete(record_id):
                messagebox.showinfo(
                    "Не найдено",
                    f"Запись с ID {record_id} не найдена.",
                    parent=self,
                )
                return
            self.clear_form()
            self.refresh_records()
            messagebox.showinfo("Готово", "Запись удалена.", parent=self)

        self._run(delete)

    def refresh_records(self) -> None:
        def refresh() -> None:
            records = self.spec.read_all()
            user_names = {}
            if any(
                name == "user_name"
                for name, _ in self.spec.additional_columns
            ):
                user_names = {
                    user["id"]: user["full_name"]
                    for user in backend.get_users()
                }
            for item in self.tree.get_children():
                self.tree.delete(item)
            columns = (
                "id",
                *(field.name for field in self.spec.fields),
                *(name for name, _ in self.spec.additional_columns),
                "created_at",
            )
            for record in records:
                display_record = {
                    **record,
                    "user_name": user_names.get(
                        record.get("user_id"),
                        f"Пользователь не найден (ID {record.get('user_id')})",
                    ),
                }
                values = []
                for column in columns:
                    value = display_record.get(column)
                    values.append(value.value if isinstance(value, Enum) else value)
                self.tree.insert("", tk.END, values=values)

        self._run(refresh)

    def _show_record(self, record: dict[str, Any]) -> None:
        self.record_id.set(str(record.get("id", "")))
        for field in self.spec.fields:
            value = record.get(field.name)
            if isinstance(value, Enum):
                value = value.value
            widget = self.inputs[field.name]
            widget_value = "" if value is None else str(value)
            if isinstance(widget, ttk.Combobox):
                widget.set(widget_value)
            else:
                widget.delete(0, tk.END)
                widget.insert(0, widget_value)

    def _select_record(self, event: tk.Event) -> None:
        if event.widget is not self.tree:
            return
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0], "values")
        record_id = int(values[0])
        self._run(lambda: self._show_record_or_fetch(record_id))

    def _show_record_or_fetch(self, record_id: int) -> None:
        record = self.spec.read(record_id)
        if record is None:
            raise ValueError(f"Запись с ID {record_id} больше не существует.")
        self._show_record(record)

    def clear_form(self) -> None:
        self.record_id.set("")
        for field in self.spec.fields:
            widget = self.inputs[field.name]
            if isinstance(widget, ttk.Combobox):
                widget.current(0)
            else:
                widget.delete(0, tk.END)


class BookingApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Система бронирования столиков")
        self.geometry("1120x720")
        self.minsize(850, 560)
        self._configure_style()
        self._build_interface()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Title.TLabel", font=("TkDefaultFont", 16, "bold"))
        style.configure("TButton", padding=(8, 5))

    def _build_interface(self) -> None:
        header = ttk.Frame(self, padding=(16, 14))
        header.pack(fill=tk.X)
        ttk.Label(
            header,
            text="Бронирование столиков",
            style="Title.TLabel",
        ).pack(side=tk.LEFT)
        ttk.Button(
            header,
            text="Создать таблицы БД",
            command=self.create_tables,
        ).pack(side=tk.RIGHT)
        ttk.Button(
            header,
            text="Заполнить БД тестовыми данными",
            command=self.seed_test_data,
        ).pack(side=tk.RIGHT, padx=(0, 8))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self.entity_tabs: list[EntityTab] = []
        for spec in ENTITY_SPECS:
            tab = EntityTab(self.notebook, spec)
            self.notebook.add(tab, text=spec.title)
            self.entity_tabs.append(tab)
        self.notebook.bind("<<NotebookTabChanged>>", self._refresh_selected_tab)
        self.after(100, self._refresh_all_tabs)

    def _refresh_all_tabs(self) -> None:
        for tab in self.entity_tabs:
            tab.refresh_records()

    def _refresh_selected_tab(self, event: tk.Event) -> None:
        if event.widget is not self.notebook:
            return
        selected_tab = self.notebook.nametowidget(self.notebook.select())
        if selected_tab in self.entity_tabs:
            selected_tab.refresh_records()

    def create_tables(self) -> None:
        try:
            backend.create_tables()
        except Exception as error:
            messagebox.showerror(
                "Не удалось создать таблицы",
                f"{type(error).__name__}: {error}",
                parent=self,
            )
            return
        messagebox.showinfo(
            "Готово",
            "Таблицы users, tables и bookings созданы или уже существуют.",
            parent=self,
        )

    def seed_test_data(self) -> None:
        if not messagebox.askyesno(
            "Добавить тестовые данные",
            "Будут добавлены 5 пользователей, 10 столов и 2–4 бронирования "
            "для каждого пользователя. Продолжить?",
            parent=self,
        ):
            return

        try:
            users_added, tables_added, bookings_added = seed_database()
        except Exception as error:
            messagebox.showerror(
                "Не удалось заполнить базу",
                f"{type(error).__name__}: {error}",
                parent=self,
            )
            return

        for tab in self.entity_tabs:
            tab.refresh_records()
        messagebox.showinfo(
            "Тестовые данные добавлены",
            f"Пользователей: {users_added}\n"
            f"Столов: {tables_added}\n"
            f"Бронирований: {bookings_added}",
            parent=self,
        )


if __name__ == "__main__":
    BookingApp().mainloop()
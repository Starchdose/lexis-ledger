import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
import json
import os
import sys
import calendar
from typing import List, Optional
from zoneinfo import ZoneInfo

DATA_FILE = "planner_data.json"
PRIORITY_LEVELS = ["P0", "P1", "P2", "P3"]
RECURRING_SYMBOLS = ["★", "♥", "◆", "●", "■"]
COMMON_TIMEZONES = [
    "UTC",
    "Europe/Paris",
    "Europe/London",
    "America/New_York",
    "America/Los_Angeles",
    "Asia/Hong_Kong",
    "Asia/Shanghai",
    "Asia/Tokyo",
    "Asia/Singapore",
]


def resource_path(relative_path: str) -> str:
    """
    Get absolute path to resource, works for dev and PyInstaller (frozen exe).
    """
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


@dataclass
class Settings:
    active_timezone: str
    use_system_timezone: bool
    color_p0: str
    color_p1: str
    color_p2: str
    color_p3: str
    color_overdue: str
    color_success: str
    color_failed: str
    color_recurring: str


def get_system_timezone_name() -> str:
    try:
        tz = datetime.now().astimezone().tzinfo
        key = getattr(tz, "key", None)
        if key is not None:
            return key
        return str(tz)
    except Exception:
        return "UTC"


def default_settings() -> Settings:
    return Settings(
        active_timezone=get_system_timezone_name(),
        use_system_timezone=True,
        color_p0="#ff4d4d",     # bright red
        color_p1="#ff9933",     # orange
        color_p2="#ffd633",     # yellow
        color_p3="#66b3ff",     # blue
        color_overdue="#cc0000",
        color_success="#888888",
        color_failed="#990099",
        color_recurring="#00aa88",
    )


def settings_to_dict(s: Settings) -> dict:
    return asdict(s)


def dict_to_settings(d: dict) -> Settings:
    base = default_settings()
    for field in (
        "active_timezone",
        "use_system_timezone",
        "color_p0",
        "color_p1",
        "color_p2",
        "color_p3",
        "color_overdue",
        "color_success",
        "color_failed",
        "color_recurring",
    ):
        if field in d:
            setattr(base, field, d[field])
    return base


@dataclass
class Task:
    id: int
    title: str
    description: str
    start_date: date
    end_date: Optional[date]
    manual_priority: Optional[str]  # "P0".."P3" or None
    status: str  # "active", "success", "failed"
    closed_date: Optional[date]
    source_timezone: str = ""       # info-only: timezone used when creating task

    def is_overdue(self, today: date) -> bool:
        return (
            self.status == "active"
            and self.end_date is not None
            and today > self.end_date
        )

    def auto_priority(self, today: date) -> str:
        """Automatic priority based on how close end_date is to today."""
        if self.end_date is None:
            return "P3"
        days_diff = (self.end_date - today).days
        if days_diff <= 2:
            return "P0"
        elif days_diff <= 7:
            return "P1"
        elif days_diff <= 30:
            return "P2"
        else:
            return "P3"

    def effective_priority(self, today: date) -> str:
        """Manual priority overrides auto; otherwise auto."""
        return self.manual_priority or self.auto_priority(today)


@dataclass
class RecurringTask:
    id: int
    title: str
    description: str
    start_date: date
    end_date: Optional[date]
    symbol: str
    active: bool
    completed_dates: List[date]


def task_to_dict(task: Task) -> dict:
    d = asdict(task)
    d["start_date"] = task.start_date.isoformat()
    d["end_date"] = task.end_date.isoformat() if task.end_date else None
    d["closed_date"] = task.closed_date.isoformat() if task.closed_date else None
    return d


def dict_to_task(d: dict) -> Task:
    return Task(
        id=d["id"],
        title=d["title"],
        description=d.get("description", ""),
        start_date=date.fromisoformat(d["start_date"]),
        end_date=date.fromisoformat(d["end_date"]) if d.get("end_date") else None,
        manual_priority=d.get("manual_priority"),
        status=d.get("status", "active"),
        closed_date=date.fromisoformat(d["closed_date"]) if d.get("closed_date") else None,
        source_timezone=d.get("source_timezone", ""),
    )


def recurring_to_dict(r: RecurringTask) -> dict:
    return {
        "id": r.id,
        "title": r.title,
        "description": r.description,
        "start_date": r.start_date.isoformat(),
        "end_date": r.end_date.isoformat() if r.end_date else None,
        "symbol": r.symbol,
        "active": r.active,
        "completed_dates": [d.isoformat() for d in r.completed_dates],
    }


def dict_to_recurring(d: dict) -> RecurringTask:
    return RecurringTask(
        id=d["id"],
        title=d["title"],
        description=d.get("description", ""),
        start_date=date.fromisoformat(d["start_date"]),
        end_date=date.fromisoformat(d["end_date"]) if d.get("end_date") else None,
        symbol=d.get("symbol", RECURRING_SYMBOLS[0]),
        active=d.get("active", True),
        completed_dates=[
            date.fromisoformat(s) for s in d.get("completed_dates", [])
        ],
    )


class DatePicker(tk.Toplevel):
    """Simple date picker dialog with month navigation."""

    def __init__(self, master, initial_date: date, on_selected):
        super().__init__(master)
        self.title("Select date")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self.on_selected = on_selected
        self.year = initial_date.year
        self.month = initial_date.month

        self._build_widgets()
        self._draw_calendar()

    def _build_widgets(self):
        header = ttk.Frame(self)
        header.pack(fill="x", pady=5)

        self.month_label_var = tk.StringVar()
        prev_btn = ttk.Button(header, text="<", width=3, command=self._prev_month)
        prev_btn.pack(side="left", padx=5)

        month_lbl = ttk.Label(header, textvariable=self.month_label_var, font=("Segoe UI", 10, "bold"))
        month_lbl.pack(side="left", expand=True)

        next_btn = ttk.Button(header, text=">", width=3, command=self._next_month)
        next_btn.pack(side="right", padx=5)

        self.cal_frame = ttk.Frame(self)
        self.cal_frame.pack(padx=5, pady=5)

    def _draw_calendar(self):
        for child in self.cal_frame.winfo_children():
            child.destroy()

        # Month label
        self.month_label_var.set(f"{calendar.month_name[self.month]} {self.year}")

        # Weekday headers (Mon-Sun)
        days = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        for col, name in enumerate(days):
            lbl = ttk.Label(self.cal_frame, text=name, anchor="center")
            lbl.grid(row=0, column=col, padx=2, pady=2)

        first_weekday, num_days = calendar.monthrange(self.year, self.month)
        # first_weekday: Monday=0, Sunday=6

        row = 1
        col = first_weekday
        for day in range(1, num_days + 1):
            btn = ttk.Button(
                self.cal_frame,
                text=str(day),
                width=3,
                command=lambda d=day: self._select_date(d)
            )
            btn.grid(row=row, column=col, padx=1, pady=1)
            col += 1
            if col > 6:
                col = 0
                row += 1

    def _prev_month(self):
        self.month -= 1
        if self.month == 0:
            self.month = 12
            self.year -= 1
        self._draw_calendar()

    def _next_month(self):
        self.month += 1
        if self.month == 13:
            self.month = 1
            self.year += 1
        self._draw_calendar()

    def _select_date(self, day: int):
        selected = date(self.year, self.month, day)
        try:
            self.on_selected(selected)
        finally:
            self.destroy()


class PlannerApp(tk.Tk):
    def __init__(self):
        super().__init__()

        # --- Window / taskbar icon ---
        try:
            icon_path = resource_path("lexisledger.ico")
            self.iconbitmap(icon_path)
        except Exception as e:
            print("Could not set window icon:", e)

        self.title("LexisLedger")
        self.geometry("1100x650")
        self.minsize(900, 600)

        self.settings: Settings = default_settings()
        self.tasks: List[Task] = []
        self.recurring_tasks: List[RecurringTask] = []
        self.next_task_id = 1
        self.next_recurring_id = 1
        self.last_popup_date: Optional[date] = None

        self.today = date.today()
        self.current_date = self.today

        # For day-view highlighting
        self.day_view_task_labels: dict[int, tk.Frame] = {}
        self.highlighted_task_id: Optional[int] = None

        # Paned + left frame references (set in _create_widgets)
        self.main_paned: Optional[ttk.PanedWindow] = None
        self.left_frame: Optional[ttk.Frame] = None

        self.load_data()
        self._create_widgets()
        self.refresh_views()
        # Show overdue popup after initial layout
        self.after(300, self.maybe_show_overdue_popup)
        # Enforce minimum width for the left pane so buttons don't disappear
        self.after(400, self._enforce_left_min_width)

    # ---------- Settings-based helpers ----------
    def _update_today_from_settings(self):
        if self.settings.use_system_timezone:
            self.today = date.today()
        else:
            try:
                tz = ZoneInfo(self.settings.active_timezone)
                self.today = datetime.now(tz).date()
            except Exception:
                self.today = date.today()

    def get_priority_color(self, priority: str) -> str:
        if priority == "P0":
            return self.settings.color_p0
        if priority == "P1":
            return self.settings.color_p1
        if priority == "P2":
            return self.settings.color_p2
        if priority == "P3":
            return self.settings.color_p3
        return "black"

    def get_task_color(self, task: Task) -> str:
        # Used e.g. in overdue popup
        if task.status == "success":
            return self.settings.color_success
        if task.status == "failed":
            return self.settings.color_failed
        if task.is_overdue(self.today):
            return self.settings.color_overdue
        pr = task.effective_priority(self.today)
        return self.get_priority_color(pr)

    def configure_treeview_tags(self):
        # Priority → colored background, black text (so task name stays black)
        self.task_tree.tag_configure("P0", foreground="black", background=self.settings.color_p0)
        self.task_tree.tag_configure("P1", foreground="black", background=self.settings.color_p1)
        self.task_tree.tag_configure("P2", foreground="black", background=self.settings.color_p2)
        self.task_tree.tag_configure("P3", foreground="black", background=self.settings.color_p3)
        # Special states override color
        self.task_tree.tag_configure("overdue", foreground=self.settings.color_overdue, background="")
        self.task_tree.tag_configure("success", foreground=self.settings.color_success, background="")
        self.task_tree.tag_configure("failed", foreground=self.settings.color_failed, background="")
        self.task_tree.tag_configure("recurring", foreground="black", background="")

    # ---------- Enforce minimum width for To-Do pane ----------
    def _enforce_left_min_width(self):
        """
        Keeps the left (To-Do) pane from becoming too narrow when the user drags
        the sash toward the right. This prevents buttons from disappearing.
        """
        try:
            if self.main_paned is not None and self.left_frame is not None:
                if self.main_paned.winfo_exists() and self.left_frame.winfo_exists():
                    min_width = 360
                    current = self.left_frame.winfo_width()
                    total = self.main_paned.winfo_width()
                    if total > 0 and current < min_width:
                        # Move sash so left pane is at least min_width
                        self.main_paned.sash_place(0, min_width, 0)
        except Exception:
            pass

        # keep enforcing over time
        if self.main_paned is not None:
            self.after(400, self._enforce_left_min_width)

    # ---------- Data persistence ----------
    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                tasks_list = raw.get("tasks", [])
                self.tasks = [dict_to_task(t) for t in tasks_list]
                if self.tasks:
                    self.next_task_id = max(t.id for t in self.tasks) + 1

                rec_list = raw.get("recurring_tasks", [])
                self.recurring_tasks = [dict_to_recurring(r) for r in rec_list]
                if self.recurring_tasks:
                    self.next_recurring_id = max(r.id for r in self.recurring_tasks) + 1

                settings_raw = raw.get("settings")
                if settings_raw:
                    self.settings = dict_to_settings(settings_raw)

                lp = raw.get("last_popup_date")
                if lp:
                    try:
                        self.last_popup_date = date.fromisoformat(lp)
                    except Exception:
                        self.last_popup_date = None
            except Exception as e:
                print("Error loading data:", e)
                self.tasks = []
                self.recurring_tasks = []
                self.last_popup_date = None
        else:
            self.tasks = []
            self.recurring_tasks = []
            self.last_popup_date = None

    def save_data(self):
        data = {
            "tasks": [task_to_dict(t) for t in self.tasks],
            "recurring_tasks": [recurring_to_dict(r) for r in self.recurring_tasks],
            "settings": settings_to_dict(self.settings),
            "last_popup_date": self.last_popup_date.isoformat() if self.last_popup_date else None,
        }
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print("Error saving data:", e)

    # ---------- Overdue popup ----------
    def maybe_show_overdue_popup(self):
        self._update_today_from_settings()
        if self.last_popup_date == self.today:
            return  # user already suppressed popup today

        overdue_tasks = [t for t in self.tasks if t.is_overdue(self.today)]
        if not overdue_tasks:
            return

        win = tk.Toplevel(self)
        win.title("Overdue Tasks Reminder")
        win.grab_set()

        msg = ttk.Label(
            win,
            text="You have overdue tasks:",
            font=("Segoe UI", 10, "bold")
        )
        msg.pack(anchor="w", padx=10, pady=(10, 5))

        list_frame = ttk.Frame(win)
        list_frame.pack(fill="both", expand=True, padx=10)

        for t in overdue_tasks:
            days_over = (self.today - (t.end_date or self.today)).days
            txt = f"[{t.effective_priority(self.today)}] {t.title}"
            if t.end_date:
                txt += f" (due {t.end_date.isoformat()}, {days_over} days overdue)"
            lbl = ttk.Label(
                list_frame,
                text=txt,
                foreground=self.get_task_color(t),
                wraplength=400,
                justify="left"
            )
            lbl.pack(anchor="w")

        dont_var = tk.BooleanVar(value=False)
        chk = ttk.Checkbutton(
            win,
            text="Don't show this reminder again today",
            variable=dont_var
        )
        chk.pack(anchor="w", padx=10, pady=(5, 5))

        def on_ok():
            if dont_var.get():
                self.last_popup_date = self.today
                self.save_data()
            win.destroy()

        ok_btn = ttk.Button(win, text="OK", command=on_ok)
        ok_btn.pack(pady=(0, 10))

    # ---------- UI creation ----------
    def _create_widgets(self):
        # Top bar
        top_bar = ttk.Frame(self)
        top_bar.pack(side="top", fill="x")

        today_btn = ttk.Button(top_bar, text="Today", command=self.go_today)
        today_btn.pack(side="left", padx=5, pady=5)

        prev_btn = ttk.Button(top_bar, text="<", width=3, command=self.go_prev)
        prev_btn.pack(side="left")

        next_btn = ttk.Button(top_bar, text=">", width=3, command=self.go_next)
        next_btn.pack(side="left")

        self.date_label_var = tk.StringVar()
        date_label = ttk.Label(
            top_bar, textvariable=self.date_label_var, font=("Segoe UI", 12, "bold")
        )
        date_label.pack(side="left", padx=10)

        # Settings button
        settings_btn = ttk.Button(top_bar, text="Settings", command=self.open_settings_window)
        settings_btn.pack(side="right", padx=5)

        # View toggle (Day / Month)
        self.view_var = tk.StringVar(value="day")
        for view in ("day", "month"):
            rb = ttk.Radiobutton(
                top_bar,
                text=view.capitalize(),
                variable=self.view_var,
                value=view,
                command=self.refresh_views,
            )
            rb.pack(side="right", padx=4)

        # Main pane
        self.main_paned = ttk.PanedWindow(self, orient="horizontal")
        self.main_paned.pack(fill="both", expand=True)

        # Left: tasks
        self.left_frame = ttk.Frame(self.main_paned, padding=5)
        self.main_paned.add(self.left_frame, weight=1)

        header = ttk.Label(self.left_frame, text="Tasks", font=("Segoe UI", 12, "bold"))
        header.pack(anchor="w")

                # Row 1: main actions
        btn_row1 = ttk.Frame(self.left_frame)
        btn_row1.pack(fill="x", pady=(4, 0))

        add_btn = ttk.Button(btn_row1, text="+ New Task", command=self.open_new_task_window)
        add_btn.pack(side="left")

        mark_done_btn = ttk.Button(
            btn_row1, text="Mark Done", command=self.on_mark_done_clicked
        )
        mark_done_btn.pack(side="left", padx=4)

        mark_failed_btn = ttk.Button(
            btn_row1, text="Mark Failed", command=self.on_mark_failed_clicked
        )
        mark_failed_btn.pack(side="left", padx=4)

        reactivate_btn = ttk.Button(
            btn_row1, text="Re-activate", command=self.on_reactivate_clicked
        )
        reactivate_btn.pack(side="left", padx=4)

        delete_btn = ttk.Button(btn_row1, text="Delete", command=self.on_delete_clicked)
        delete_btn.pack(side="left", padx=4)

        recurring_btn = ttk.Button(
            btn_row1, text="Add Recurring", command=self.open_new_recurring_window
        )
        recurring_btn.pack(side="left", padx=4)

        # Row 2: filter (one-off vs recurring)
        btn_row2 = ttk.Frame(self.left_frame)
        btn_row2.pack(fill="x", pady=(2, 4))

        filter_label = ttk.Label(btn_row2, text="Filter:")
        filter_label.pack(side="left", padx=(0, 2))
        self.filter_var = tk.StringVar(value="All")
        filter_combo = ttk.Combobox(
            btn_row2,
            textvariable=self.filter_var,
            values=["All", "Only one-off", "Only recurring"],
            width=14,
            state="readonly",
        )
        filter_combo.pack(side="left", padx=2)
        filter_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_views())


        # Priority filter + reverse order + hide closed
        prio_frame = ttk.Frame(self.left_frame)
        prio_frame.pack(fill="x", pady=(2, 4))

        ttk.Label(prio_frame, text="Priorities:").pack(side="left")

        self.prio_filter_vars = {}
        for pr in PRIORITY_LEVELS:
            var = tk.BooleanVar(value=True)
            self.prio_filter_vars[pr] = var
            cb = ttk.Checkbutton(prio_frame, text=pr, variable=var, command=self.refresh_views)
            cb.pack(side="left", padx=2)

        self.reverse_sort_var = tk.BooleanVar(value=False)
        rev_cb = ttk.Checkbutton(
            prio_frame,
            text="Reverse order",
            variable=self.reverse_sort_var,
            command=self.refresh_views,
        )
        rev_cb.pack(side="right")

        self.hide_closed_var = tk.BooleanVar(value=False)
        hide_cb = ttk.Checkbutton(
            prio_frame,
            text="Hide closed",
            variable=self.hide_closed_var,
            command=self.refresh_views,
        )
        hide_cb.pack(side="right", padx=5)

        # Treeview: now with Title and Closed columns
        columns = ("title", "priority", "start", "end", "closed", "status")
        self.task_tree = ttk.Treeview(
            self.left_frame, columns=columns, show="headings", selectmode="browse"
        )
        self.task_tree.heading("title", text="Title")
        self.task_tree.heading("priority", text="Priority/Symbol")
        self.task_tree.heading("start", text="Start")
        self.task_tree.heading("end", text="End")
        self.task_tree.heading("closed", text="Closed")
        self.task_tree.heading("status", text="Status")

        self.task_tree.column("title", width=220, anchor="w")
        self.task_tree.column("priority", width=90, anchor="center")
        self.task_tree.column("start", width=90, anchor="center")
        self.task_tree.column("end", width=90, anchor="center")
        self.task_tree.column("closed", width=90, anchor="center")
        self.task_tree.column("status", width=110, anchor="center")


        self.task_tree.pack(fill="both", expand=True, pady=4)

        # Bind selection and double-click
        self.task_tree.bind("<<TreeviewSelect>>", self.on_task_tree_select)
        self.task_tree.bind("<Double-1>", self.on_task_tree_double_click)

        # Apply initial tag colors
        self.configure_treeview_tags()

        # Right: calendar container
        right_frame = ttk.Frame(self.main_paned, padding=5)
        self.main_paned.add(right_frame, weight=2)

        self.calendar_container = ttk.Frame(right_frame)
        self.calendar_container.pack(fill="both", expand=True)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w")
        status_bar.pack(side="bottom", fill="x")

    # ---------- Calendar navigation ----------
    def go_today(self):
        self._update_today_from_settings()
        self.current_date = self.today
        self.refresh_views()

    def go_prev(self):
        if self.view_var.get() == "day":
            self.current_date = self.current_date - timedelta(days=1)
        else:
            month = self.current_date.month - 1
            year = self.current_date.year
            if month == 0:
                month = 12
                year -= 1
            self.current_date = self.current_date.replace(year=year, month=month, day=1)
        self.refresh_views()

    def go_next(self):
        if self.view_var.get() == "day":
            self.current_date = self.current_date + timedelta(days=1)
        else:
            month = self.current_date.month + 1
            year = self.current_date.year
            if month == 13:
                month = 1
                year += 1
            self.current_date = self.current_date.replace(year=year, month=month, day=1)
        self.refresh_views()

    # ---------- Highlight handling ----------
    def _set_row_bg(self, row_frame: tk.Frame, bg: str):
        try:
            row_frame.config(bg=bg)
        except Exception:
            pass
        for child in row_frame.winfo_children():
            try:
                child.config(bg=bg)
            except Exception:
                pass

    def set_highlighted_task(self, task_id: Optional[int]):
        # reset previous
        if self.highlighted_task_id is not None:
            old_id = self.highlighted_task_id
            row = self.day_view_task_labels.get(old_id)
            if row is not None:
                self._set_row_bg(row, "SystemButtonFace")

        self.highlighted_task_id = task_id

        if task_id is not None:
            row = self.day_view_task_labels.get(task_id)
            if row is not None:
                self._set_row_bg(row, "lightyellow")

    # ---------- Refresh views ----------
    def refresh_views(self):
        self._update_today_from_settings()

        self.date_label_var.set(self.current_date.strftime("%A, %d %B %Y"))

        # task/recurring table
        for item in self.task_tree.get_children():
            self.task_tree.delete(item)

        filter_val = self.filter_var.get() if hasattr(self, "filter_var") else "All"

        # One-off tasks
        if filter_val in ("All", "Only one-off"):
            reverse = self.reverse_sort_var.get()
            sorted_tasks = sorted(
                self.tasks,
                key=lambda t: (t.effective_priority(self.today), t.end_date or date.max),
                reverse=reverse,
            )
            for task in sorted_tasks:
                # hide closed if requested
                if self.hide_closed_var.get() and task.status in ("success", "failed"):
                    continue

                pr = task.effective_priority(self.today)
                # priority filter
                if not self.prio_filter_vars.get(pr, tk.BooleanVar(value=True)).get():
                    continue

                start_str = task.start_date.isoformat()
                end_str = task.end_date.isoformat() if task.end_date else "-"
                closed_str = task.closed_date.isoformat() if task.closed_date else "-"
                status_str = "Overdue" if task.is_overdue(self.today) else task.status.capitalize()

                tags: List[str] = []
                if task.status == "success":
                    tags.append("success")
                elif task.status == "failed":
                    tags.append("failed")
                elif task.is_overdue(self.today):
                    tags.append("overdue")
                else:
                    # active, non-overdue → colored by priority (background)
                    tags.append(pr)

                row_id = f"T{task.id}"
                self.task_tree.insert(
                    "",
                    "end",
                    iid=row_id,
                    values=(task.title, pr, start_str, end_str, closed_str, status_str),
                    tags=tags,
                )


        # Recurring tasks
        if filter_val in ("All", "Only recurring"):
            sorted_rec = sorted(
                self.recurring_tasks,
                key=lambda r: (r.start_date, r.title.lower()),
            )
            for r in sorted_rec:
                start_str = r.start_date.isoformat()
                end_str = r.end_date.isoformat() if r.end_date else "-"
                status_str = "Recurring (active)" if r.active else "Recurring (inactive)"
                row_id = f"R{r.id}"
                self.task_tree.insert(
                    "",
                    "end",
                    iid=row_id,
                    values=(r.title, r.symbol, start_str, end_str, status_str),
                    tags=["recurring"],
                )

        # clear calendar and day-view labels mapping
        for child in self.calendar_container.winfo_children():
            child.destroy()
        self.day_view_task_labels = {}

        if self.view_var.get() == "day":
            self._build_day_view()
        else:
            self._build_month_view()

        self.save_data()

    # ---------- Day view helpers ----------
    def _add_task_label_to_day_view(self, frame, task: Task):
        pr = task.effective_priority(self.today)

        row_frame = tk.Frame(frame, bg="SystemButtonFace")
        row_frame.pack(anchor="w", fill="x")

        pr_label = tk.Label(
            row_frame,
            text=f"[{pr}]",
            fg=self.get_priority_color(pr),
            bg="SystemButtonFace",
            anchor="w",
        )
        pr_label.pack(side="left")

        title_text = f" {task.title}"
        if task.is_overdue(self.today):
            title_text += " (OVERDUE)"

        title_label = tk.Label(
            row_frame,
            text=title_text,
            fg="black",
            bg="SystemButtonFace",
            anchor="w",
            justify="left",
        )
        title_label.pack(side="left", fill="x")

        # store for highlighting
        self.day_view_task_labels[task.id] = row_frame

        def on_click(event, tid=task.id):
            # select in tree and highlight
            row_id = f"T{tid}"
            if row_id in self.task_tree.get_children():
                self.task_tree.selection_set(row_id)
                self.task_tree.see(row_id)
            self.set_highlighted_task(tid)

        def on_double_click(event, task_obj=task):
            self.open_edit_task_window(task_obj)

        # Bind to frame and children
        row_frame.bind("<Button-1>", on_click)
        row_frame.bind("<Double-1>", on_double_click)
        pr_label.bind("<Button-1>", on_click)
        pr_label.bind("<Double-1>", on_double_click)
        title_label.bind("<Button-1>", on_click)
        title_label.bind("<Double-1>", on_double_click)

    # ---------- Day view ----------
    def _build_day_view(self):
        frame = self.calendar_container
        header = ttk.Label(
            frame,
            text=f"Day view: {self.current_date.isoformat()}",
            font=("Segoe UI", 12, "bold"),
        )
        header.pack(anchor="w")

        tasks_today = self.tasks_for_day(self.current_date, include_history=False)

        # Split and sort by effective priority (P0→P1→P2→P3) and end_date
        urgent_tasks = [t for t in tasks_today if t.effective_priority(self.today) in ("P0", "P1")]
        long_term_tasks = [t for t in tasks_today if t.effective_priority(self.today) in ("P2", "P3")]

        urgent_tasks = sorted(
            urgent_tasks,
            key=lambda t: (t.effective_priority(self.today), t.end_date or date.max),
        )
        long_term_tasks = sorted(
            long_term_tasks,
            key=lambda t: (t.effective_priority(self.today), t.end_date or date.max),
        )

        # Urgent section
        urgent_label = ttk.Label(
            frame,
            text="Urgent tasks (P0–P1) today:",
            font=("Segoe UI", 10, "bold"),
        )
        urgent_label.pack(anchor="w", pady=(10, 0))

        if urgent_tasks:
            for t in urgent_tasks:
                self._add_task_label_to_day_view(frame, t)
        else:
            ttk.Label(frame, text="(none)").pack(anchor="w")

        # Long-term section
        long_label = ttk.Label(
            frame,
            text="Long-term tasks (P2–P3) today:",
            font=("Segoe UI", 10, "bold"),
        )
        long_label.pack(anchor="w", pady=(10, 0))

        if long_term_tasks:
            for t in long_term_tasks:
                self._add_task_label_to_day_view(frame, t)
        else:
            ttk.Label(frame, text="(none)").pack(anchor="w")


        # Recurring tasks section
        recur_label = ttk.Label(
            frame,
            text="Recurring tasks today:",
            font=("Segoe UI", 10, "bold"),
        )
        recur_label.pack(anchor="w", pady=(10, 0))

        recurs = self.recurring_for_day(self.current_date)
        if recurs:
            for r in recurs:
                done = self.is_recurring_done_on(r, self.current_date)
                var = tk.BooleanVar(value=done)
                cb = ttk.Checkbutton(
                    frame,
                    text=f"{r.symbol} {r.title}",
                    variable=var
                )

                def on_toggle(rt=r, v=var, day=self.current_date):
                    self.set_recurring_done_on(rt, day, v.get())

                cb.config(command=on_toggle)
                cb.pack(anchor="w")
        else:
            ttk.Label(frame, text="(none)").pack(anchor="w")

        # Closed tasks section
        closed_today = self.tasks_closed_on(self.current_date)

        hist_label = ttk.Label(
            frame,
            text="Closed tasks today:",
            font=("Segoe UI", 10, "bold"),
        )
        hist_label.pack(anchor="w", pady=(10, 0))

        if closed_today:
            for task in closed_today:
                state = "✓ success" if task.status == "success" else "✗ failed"
                txt = f"{task.title} ({state})"
                color = (
                    self.settings.color_success
                    if task.status == "success"
                    else self.settings.color_failed
                )

                # Make historical entries clickable & highlightable
                row_label = ttk.Label(frame, text=txt, foreground=color)
                row_label.pack(anchor="w")

                # map for highlight / cross-selection
                self.day_view_task_labels[task.id] = row_label

                def on_click(event, tid=task.id):
                    row_id = f"T{tid}"
                    if row_id in self.task_tree.get_children():
                        self.task_tree.selection_set(row_id)
                        self.task_tree.see(row_id)
                    self.set_highlighted_task(tid)

                def on_double_click(event, t_obj=task):
                    self.open_edit_task_window(t_obj)

                row_label.bind("<Button-1>", on_click)
                row_label.bind("<Double-1>", on_double_click)
        else:
            ttk.Label(frame, text="(none)").pack(anchor="w")

        # Re-apply highlight if still relevant
        if self.highlighted_task_id is not None:
            self.set_highlighted_task(self.highlighted_task_id)

    # ---------- Month view ----------
    def _build_month_view(self):
        frame = self.calendar_container
        header = ttk.Label(
            frame,
            text=f"Month view: {self.current_date.strftime('%B %Y')}",
            font=("Segoe UI", 12, "bold"),
        )
        header.pack(anchor="w")

        # weekday headers
        weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        header_row = ttk.Frame(frame)
        header_row.pack(fill="x")
        for wd in weekdays:
            lbl = ttk.Label(header_row, text=wd, anchor="center")
            lbl.pack(side="left", expand=True, fill="x")

        first_of_month = self.current_date.replace(day=1)
        start_weekday = first_of_month.weekday()  # Monday=0

        # days in month
        if first_of_month.month == 12:
            next_month = first_of_month.replace(
                year=first_of_month.year + 1, month=1, day=1
            )
        else:
            next_month = first_of_month.replace(
                month=first_of_month.month + 1, day=1
            )
        num_days = (next_month - first_of_month).days

        day = 1
        for week in range(6):
            row_frame = ttk.Frame(frame)
            row_frame.pack(fill="x", expand=True)
            for wd in range(7):
                cell = ttk.Frame(row_frame, borderwidth=1, relief="solid")
                cell.pack(side="left", expand=True, fill="both", padx=1, pady=1)

                if week == 0 and wd < start_weekday:
                    continue
                if day > num_days:
                    continue

                cell_date = first_of_month.replace(day=day)

                d_lbl = ttk.Label(cell, text=str(day))
                d_lbl.pack(anchor="nw")

                # dots summary area
                pr_counts, success_count, failed_count, overdue_count = self.get_day_summary(cell_date)
                has_any = any(count > 0 for count in pr_counts.values()) or success_count or failed_count or overdue_count

                if has_any:
                    dots_frame = ttk.Frame(cell)
                    dots_frame.pack(anchor="center")

                    # priority dots (one dot per task at that priority)
                    for pr in PRIORITY_LEVELS:
                        count = pr_counts[pr]
                        if count:
                            ttk.Label(
                                dots_frame,
                                text="•" * count,
                                foreground=self.get_priority_color(pr),
                            ).pack(side="left")

                    # overdue dots (separate color)
                    if overdue_count:
                        ttk.Label(
                            dots_frame,
                            text="•" * overdue_count,
                            foreground=self.settings.color_overdue,
                        ).pack(side="left")

                    # success dots
                    if success_count:
                        ttk.Label(
                            dots_frame,
                            text="•" * success_count,
                            foreground=self.settings.color_success,
                        ).pack(side="left")

                    # failed dots
                    if failed_count:
                        ttk.Label(
                            dots_frame,
                            text="•" * failed_count,
                            foreground=self.settings.color_failed,
                        ).pack(side="left")


                # recurring symbols row
                rec_syms = self.get_recurring_symbols_for_day(cell_date)
                if rec_syms:
                    rec_frame = ttk.Frame(cell)
                    rec_frame.pack(anchor="center")
                    ttk.Label(
                        rec_frame,
                        text="".join(rec_syms),
                        foreground=self.settings.color_recurring,
                    ).pack()

                def on_click(event, d=cell_date):
                    self._on_month_day_clicked(d)

                cell.bind("<Button-1>", on_click)
                for child in cell.winfo_children():
                    child.bind("<Button-1>", on_click)

                day += 1

    def get_day_summary(self, d: date):
        # active tasks for that day
        active = [t for t in self.tasks_for_day(d, include_history=False)]
        closed = self.tasks_closed_on(d)

        # count dots per priority
        pr_counts = {pr: 0 for pr in PRIORITY_LEVELS}
        overdue_count = 0

        for t in active:
            pr = t.effective_priority(self.today)

            # If overdue → count as overdue only (no priority color)
            if t.is_overdue(self.today):
                overdue_count += 1
                continue

            if pr in ("P0", "P1"):
                # Show every P0/P1 task on each active day (if not overdue)
                pr_counts[pr] += 1
                continue

            if pr in ("P2", "P3"):
                # Show P2/P3 only:
                # - first 2 days from start
                # - last 3 days before/at end
                start = t.start_date
                end = t.end_date

                show = False
                # First two days
                if d == start or d == start + timedelta(days=1):
                    show = True

                # Last three days if we have an end date
                if end is not None:
                    last_days = {end, end - timedelta(days=1), end - timedelta(days=2)}
                    if d in last_days:
                        show = True

                # Also only within active range
                if end is not None and not (start <= d <= end):
                    show = False
                if end is None and d < start:
                    show = False

                if show:
                    pr_counts[pr] += 1

        success_count = sum(1 for t in closed if t.status == "success")
        failed_count = sum(1 for t in closed if t.status == "failed")

        return pr_counts, success_count, failed_count, overdue_count


    def get_recurring_symbols_for_day(self, d: date) -> List[str]:
        syms: List[str] = []
        for r in self.recurring_tasks:
            if r.active and r.start_date <= d and (r.end_date is None or r.end_date >= d):
                if d in r.completed_dates:
                    syms.append(r.symbol)
        return syms

    def _on_month_day_clicked(self, d: date):
        self.current_date = d
        self.view_var.set("day")
        self.refresh_views()

    # ---------- Task selection & actions ----------
    def get_selected_item(self):
        sel = self.task_tree.selection()
        if not sel:
            return None, None
        row_id = sel[0]
        if row_id.startswith("T"):
            try:
                tid = int(row_id[1:])
            except ValueError:
                return None, None
            for t in self.tasks:
                if t.id == tid:
                    return "task", t
        elif row_id.startswith("R"):
            try:
                rid = int(row_id[1:])
            except ValueError:
                return None, None
            for r in self.recurring_tasks:
                if r.id == rid:
                    return "recurring", r
        return None, None

    def get_selected_task(self) -> Optional[Task]:
        kind, obj = self.get_selected_item()
        return obj if kind == "task" else None

    def get_selected_recurring(self) -> Optional[RecurringTask]:
        kind, obj = self.get_selected_item()
        return obj if kind == "recurring" else None

    def on_task_tree_select(self, event=None):
        task = self.get_selected_task()
        if task:
            self.set_highlighted_task(task.id)
        else:
            self.set_highlighted_task(None)

    def on_task_tree_double_click(self, event=None):
        kind, obj = self.get_selected_item()
        if kind == "task" and obj is not None:
            self.open_edit_task_window(obj)
        elif kind == "recurring" and obj is not None:
            self.open_edit_recurring_window(obj)

    def on_mark_done_clicked(self):
        task = self.get_selected_task()
        if not task:
            messagebox.showinfo("No selection", "Please select a one-off task first.")
            return
        self.mark_selected_task(task, "success")

    def on_mark_failed_clicked(self):
        task = self.get_selected_task()
        if not task:
            messagebox.showinfo("No selection", "Please select a one-off task first.")
            return
        self.mark_selected_task(task, "failed")

    def on_reactivate_clicked(self):
        task = self.get_selected_task()
        if not task:
            messagebox.showinfo("No selection", "Please select a one-off task first.")
            return
        if task.status == "active":
            messagebox.showinfo("Already active", "This task is already active.")
            return
        task.status = "active"
        task.closed_date = None
        self.status_var.set(f"Task '{task.title}' re-activated.")
        self.refresh_views()

    def on_delete_clicked(self):
        kind, obj = self.get_selected_item()
        if kind == "task" and obj is not None:
            self.delete_task(obj)
        elif kind == "recurring" and obj is not None:
            self.delete_recurring(obj)
        else:
            messagebox.showinfo("No selection", "Please select an item to delete.")

    def mark_selected_task(self, task: Task, status: str):
        if status not in ("success", "failed"):
            return
        task.status = status
        self._update_today_from_settings()
        task.closed_date = self.today
        self.status_var.set(f"Task '{task.title}' marked as {status}.")
        self.refresh_views()

    def delete_task(self, task: Task):
        answer = messagebox.askyesno(
            "Delete Task",
            f"Are you sure you want to delete '{task.title}'?\nThis cannot be undone.",
        )
        if not answer:
            return
        self.tasks = [t for t in self.tasks if t.id != task.id]
        if self.highlighted_task_id == task.id:
            self.highlighted_task_id = None
        self.status_var.set(f"Task '{task.title}' deleted.")
        self.refresh_views()

    def delete_recurring(self, r: RecurringTask):
        answer = messagebox.askyesno(
            "Delete Recurring Task",
            f"Are you sure you want to delete recurring task '{r.title}'?\nThis cannot be undone.",
        )
        if not answer:
            return
        self.recurring_tasks = [x for x in self.recurring_tasks if x.id != r.id]
        self.status_var.set(f"Recurring task '{r.title}' deleted.")
        self.refresh_views()

    # ---------- Task retrieval helpers ----------
    def tasks_for_day(self, d: date, include_history: bool = False) -> List[Task]:
        result = []
        for t in self.tasks:
            if include_history:
                if t.start_date <= d and (t.end_date is None or t.end_date >= d):
                    result.append(t)
            else:
                if (
                    t.status == "active"
                    and t.start_date <= d
                    and (t.end_date is None or t.end_date >= d)
                ):
                    result.append(t)
        return result

    def tasks_closed_on(self, d: date) -> List[Task]:
        return [t for t in self.tasks if t.closed_date == d]

    # ---------- Recurring helpers ----------
    def recurring_for_day(self, d: date) -> List[RecurringTask]:
        res = []
        for r in self.recurring_tasks:
            if r.active and r.start_date <= d and (r.end_date is None or r.end_date >= d):
                res.append(r)
        return res

    def is_recurring_done_on(self, r: RecurringTask, d: date) -> bool:
        return d in r.completed_dates

    def set_recurring_done_on(self, r: RecurringTask, d: date, done: bool):
        if done:
            if d not in r.completed_dates:
                r.completed_dates.append(d)
        else:
            if d in r.completed_dates:
                r.completed_dates.remove(d)
        self.save_data()

    # ---------- Date picker helper ----------
    def _open_date_picker_for_entry(self, parent, entry: ttk.Entry):
        text = entry.get().strip()
        try:
            init = date.fromisoformat(text)
        except Exception:
            init = self.current_date

        def on_selected(d: date):
            entry.delete(0, tk.END)
            entry.insert(0, d.isoformat())

        DatePicker(parent, init, on_selected)

    # ---------- New / Edit task dialogs ----------
    def open_new_task_window(self):
        self._open_task_form(mode="new")

    def open_edit_task_window(self, task: Task):
        self._open_task_form(mode="edit", task=task)

    def _open_task_form(self, mode: str, task: Optional[Task] = None):
        is_edit = mode == "edit"
        win = tk.Toplevel(self)
        win.title("Edit Task" if is_edit else "New Task")
        win.grab_set()

        ttk.Label(win, text="Title:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        title_entry = ttk.Entry(win, width=30)
        title_entry.grid(row=0, column=1, padx=5, pady=5, columnspan=2)

        ttk.Label(win, text="Description:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        desc_entry = ttk.Entry(win, width=30)
        desc_entry.grid(row=1, column=1, padx=5, pady=5, columnspan=2)

        ttk.Label(win, text="Start date (YYYY-MM-DD):").grid(
            row=2, column=0, sticky="e", padx=5, pady=5
        )
        start_entry = ttk.Entry(win, width=15)
        start_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        start_btn = ttk.Button(
            win,
            text="📅",
            width=3,
            command=lambda: self._open_date_picker_for_entry(win, start_entry),
        )
        start_btn.grid(row=2, column=2, sticky="w", padx=2, pady=5)

        ttk.Label(win, text="End date (YYYY-MM-DD or blank):").grid(
            row=3, column=0, sticky="e", padx=5, pady=5
        )
        end_entry = ttk.Entry(win, width=15)
        end_entry.grid(row=3, column=1, sticky="w", padx=5, pady=5)
        end_btn = ttk.Button(
            win,
            text="📅",
            width=3,
            command=lambda: self._open_date_picker_for_entry(win, end_entry),
        )
        end_btn.grid(row=3, column=2, sticky="w", padx=2, pady=5)

        ttk.Label(win, text="Priority (optional):").grid(
            row=4, column=0, sticky="e", padx=5, pady=5
        )
        pr_var = tk.StringVar(value="")
        pr_combo = ttk.Combobox(
            win, textvariable=pr_var, values=["", "P0", "P1", "P2", "P3"], width=5
        )
        pr_combo.grid(row=4, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(win, text="Task timezone:").grid(
            row=5, column=0, sticky="e", padx=5, pady=5
        )
        tz_var = tk.StringVar(value=self.settings.active_timezone)
        tz_combo = ttk.Combobox(
            win, textvariable=tz_var, values=COMMON_TIMEZONES, width=25
        )
        tz_combo.grid(row=5, column=1, padx=5, pady=5, columnspan=2, sticky="w")

        # Pre-fill if edit mode
        if is_edit and task is not None:
            title_entry.insert(0, task.title)
            desc_entry.insert(0, task.description)
            start_entry.insert(0, task.start_date.isoformat())
            if task.end_date:
                end_entry.insert(0, task.end_date.isoformat())
            if task.manual_priority:
                pr_var.set(task.manual_priority)
            if task.source_timezone:
                tz_var.set(task.source_timezone)
        else:
            start_entry.insert(0, self.current_date.isoformat())

        def on_save():
            title = title_entry.get().strip()
            if not title:
                messagebox.showerror("Error", "Title is required.")
                return
            desc = desc_entry.get().strip()

            s_text = start_entry.get().strip()
            try:
                sdate = date.fromisoformat(s_text)
            except Exception:
                messagebox.showerror("Error", "Invalid start date.")
                return

            e_text = end_entry.get().strip()
            if e_text:
                try:
                    edate = date.fromisoformat(e_text)
                except Exception:
                    messagebox.showerror("Error", "Invalid end date.")
                    return
            else:
                edate = None

            pr = pr_var.get().strip() or None
            if pr and pr not in PRIORITY_LEVELS:
                messagebox.showerror("Error", "Invalid priority.")
                return

            task_tz = tz_var.get().strip() or self.settings.active_timezone

            if is_edit and task is not None:
                task.title = title
                task.description = desc
                task.start_date = sdate
                task.end_date = edate
                task.manual_priority = pr
                task.source_timezone = task_tz
                self.status_var.set(f"Task '{task.title}' updated.")
            else:
                new_task = Task(
                    id=self.next_task_id,
                    title=title,
                    description=desc,
                    start_date=sdate,
                    end_date=edate,
                    manual_priority=pr,
                    status="active",
                    closed_date=None,
                    source_timezone=task_tz,
                )
                self.tasks.append(new_task)
                self.next_task_id += 1
                self.status_var.set(f"Task '{title}' created.")

            self.refresh_views()
            win.destroy()

        save_btn = ttk.Button(win, text="Save", command=on_save)
        save_btn.grid(row=6, column=0, columnspan=3, pady=10)

    # ---------- New / Edit recurring dialogs ----------
    def open_new_recurring_window(self):
        self._open_recurring_form(mode="new")

    def open_edit_recurring_window(self, r: RecurringTask):
        self._open_recurring_form(mode="edit", rec=r)

    def _open_recurring_form(self, mode: str, rec: Optional[RecurringTask] = None):
        is_edit = mode == "edit"
        win = tk.Toplevel(self)
        win.title("Edit Recurring Task" if is_edit else "New Recurring Task")
        win.grab_set()

        ttk.Label(win, text="Title:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        title_entry = ttk.Entry(win, width=30)
        title_entry.grid(row=0, column=1, padx=5, pady=5, columnspan=2)

        ttk.Label(win, text="Description:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        desc_entry = ttk.Entry(win, width=30)
        desc_entry.grid(row=1, column=1, padx=5, pady=5, columnspan=2)

        ttk.Label(win, text="Start date (YYYY-MM-DD):").grid(
            row=2, column=0, sticky="e", padx=5, pady=5
        )
        start_entry = ttk.Entry(win, width=15)
        start_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        start_btn = ttk.Button(
            win,
            text="📅",
            width=3,
            command=lambda: self._open_date_picker_for_entry(win, start_entry),
        )
        start_btn.grid(row=2, column=2, sticky="w", padx=2, pady=5)

        ttk.Label(win, text="End date (YYYY-MM-DD or blank):").grid(
            row=3, column=0, sticky="e", padx=5, pady=5
        )
        end_entry = ttk.Entry(win, width=15)
        end_entry.grid(row=3, column=1, sticky="w", padx=5, pady=5)
        end_btn = ttk.Button(
            win,
            text="📅",
            width=3,
            command=lambda: self._open_date_picker_for_entry(win, end_entry),
        )
        end_btn.grid(row=3, column=2, sticky="w", padx=2, pady=5)

        ttk.Label(win, text="Symbol:").grid(
            row=4, column=0, sticky="e", padx=5, pady=5
        )
        sym_var = tk.StringVar(value=RECURRING_SYMBOLS[0])
        sym_combo = ttk.Combobox(
            win, textvariable=sym_var, values=RECURRING_SYMBOLS, width=5
        )
        sym_combo.grid(row=4, column=1, sticky="w", padx=5, pady=5)

        active_var = tk.BooleanVar(value=True)
        active_chk = ttk.Checkbutton(win, text="Active", variable=active_var)
        active_chk.grid(row=5, column=0, columnspan=3, sticky="w", padx=5, pady=5)

        # Pre-fill
        if is_edit and rec is not None:
            title_entry.insert(0, rec.title)
            desc_entry.insert(0, rec.description)
            start_entry.insert(0, rec.start_date.isoformat())
            if rec.end_date:
                end_entry.insert(0, rec.end_date.isoformat())
            sym_var.set(rec.symbol)
            active_var.set(rec.active)
        else:
            start_entry.insert(0, self.current_date.isoformat())

        def on_save():
            title = title_entry.get().strip()
            if not title:
                messagebox.showerror("Error", "Title is required.")
                return
            desc = desc_entry.get().strip()

            s_text = start_entry.get().strip()
            try:
                sdate = date.fromisoformat(s_text)
            except Exception:
                messagebox.showerror("Error", "Invalid start date.")
                return

            e_text = end_entry.get().strip()
            if e_text:
                try:
                    edate = date.fromisoformat(e_text)
                except Exception:
                    messagebox.showerror("Error", "Invalid end date.")
                    return
            else:
                edate = None

            sym = sym_var.get()
            if sym not in RECURRING_SYMBOLS:
                messagebox.showerror("Error", "Invalid symbol.")
                return

            active = active_var.get()

            if is_edit and rec is not None:
                rec.title = title
                rec.description = desc
                rec.start_date = sdate
                rec.end_date = edate
                rec.symbol = sym
                rec.active = active
                self.status_var.set(f"Recurring task '{rec.title}' updated.")
            else:
                new_rec = RecurringTask(
                    id=self.next_recurring_id,
                    title=title,
                    description=desc,
                    start_date=sdate,
                    end_date=edate,
                    symbol=sym,
                    active=active,
                    completed_dates=[],
                )
                self.recurring_tasks.append(new_rec)
                self.next_recurring_id += 1
                self.status_var.set(f"Recurring task '{title}' created.")

            self.save_data()
            self.refresh_views()
            win.destroy()

        save_btn = ttk.Button(win, text="Save", command=on_save)
        save_btn.grid(row=6, column=0, columnspan=3, pady=10)

    # ---------- Settings window ----------
    def open_settings_window(self):
        win = tk.Toplevel(self)
        win.title("Settings")
        win.grab_set()

        # Time zone section
        ttk.Label(win, text="Time zone:", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 2)
        )

        use_sys_var = tk.BooleanVar(value=self.settings.use_system_timezone)
        chk = ttk.Checkbutton(win, text="Use system timezone", variable=use_sys_var)
        chk.grid(row=1, column=0, columnspan=3, sticky="w", padx=20, pady=2)

        ttk.Label(win, text="Active timezone name:").grid(
            row=2, column=0, sticky="e", padx=10, pady=2
        )
        tz_var = tk.StringVar(value=self.settings.active_timezone)
        tz_entry = ttk.Entry(win, textvariable=tz_var, width=25)
        tz_entry.grid(row=2, column=1, sticky="w", padx=5, pady=2)
        tz_combo = ttk.Combobox(
            win, textvariable=tz_var, values=COMMON_TIMEZONES, width=25, state="readonly"
        )
        tz_combo.grid(row=2, column=2, sticky="w", padx=5, pady=2)

        # Colors section
        ttk.Label(win, text="Colors:", font=("Segoe UI", 10, "bold")).grid(
            row=3, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 2)
        )

        color_vars = {}
        color_blocks = {}
        color_fields = [
            ("P0 (critical)", "color_p0"),
            ("P1 (high)", "color_p1"),
            ("P2 (medium)", "color_p2"),
            ("P3 (low)", "color_p3"),
            ("Overdue", "color_overdue"),
            ("Success", "color_success"),
            ("Failed", "color_failed"),
            ("Recurring symbol", "color_recurring"),
        ]

        row = 4
        for label, attr in color_fields:
            ttk.Label(win, text=label + ":").grid(
                row=row, column=0, sticky="e", padx=10, pady=2
            )
            var = tk.StringVar(value=getattr(self.settings, attr))

            block = tk.Label(win, width=6, relief="solid")
            try:
                block.configure(bg=var.get())
            except Exception:
                block.configure(bg="#ffffff")
            block.grid(row=row, column=1, sticky="w", padx=5, pady=2)

            def make_pick(v=var, b=block):
                def _pick():
                    initial = v.get() or "#000000"
                    color = colorchooser.askcolor(initialcolor=initial)
                    if color and color[1]:
                        v.set(color[1])
                        try:
                            b.configure(bg=color[1])
                        except Exception:
                            pass
                return _pick

            pick_btn = ttk.Button(win, text="Pick…", command=make_pick())
            pick_btn.grid(row=row, column=2, sticky="w", padx=5, pady=2)

            color_vars[attr] = var
            color_blocks[attr] = block
            row += 1

        def on_save():
            self.settings.use_system_timezone = use_sys_var.get()
            tz_value = tz_var.get().strip()
            if tz_value:
                self.settings.active_timezone = tz_value

            for attr, var in color_vars.items():
                val = var.get().strip()
                if val:
                    setattr(self.settings, attr, val)

            self.configure_treeview_tags()
            self.refresh_views()
            win.destroy()

        save_btn = ttk.Button(win, text="Save", command=on_save)
        save_btn.grid(row=row, column=0, columnspan=3, pady=10)

    def on_closing(self):
        self.save_data()
        self.destroy()


def main():
    app = PlannerApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    main()

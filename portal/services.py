from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from django.contrib.auth import get_user_model
from django.db.models import Case, IntegerField, Q, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from .constants import COMMITTEES, committee_by_key, normalize_committee_key
from .models import ChatMessage, ChatTask, ChatTaskItem, Post, Video

User = get_user_model()


MAX_CHAT_MESSAGE_LENGTH = 4000
MAX_TASK_TITLE_LENGTH = 200
MAX_TASK_DESCRIPTION_LENGTH = 4000
MAX_TODO_LABEL_LENGTH = 500


@dataclass
class TaskFilter:
    status: str = ""
    priority: str = ""
    query: str = ""


@dataclass
class TaskSummary:
    total: int = 0
    todo: int = 0
    in_progress: int = 0
    blocked: int = 0
    done: int = 0
    urgent: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


@dataclass
class ChatMessageDTO:
    id: int
    author_id: int
    author_name: str
    body: str
    created_at_human: str
    is_mine: bool


@dataclass
class ChatTaskItemDTO:
    id: int
    label: str
    is_done: bool
    created_at_human: str


@dataclass
class ChatTaskDTO:
    id: int
    title: str
    description: str
    status: str
    priority: str
    due_date: str
    created_at_human: str
    updated_at_human: str
    status_label: str
    priority_label: str
    assigned_to_id: int | None
    assigned_to_name: str
    has_assignee: bool
    assigned_to_value: int
    due_date_human: str
    is_overdue: bool
    outstanding_todos: int
    completed_todos: int
    todos: list[ChatTaskItemDTO] = field(default_factory=list)


def humanize_timestamp(value) -> str:
    if not value:
        return ""
    return timezone.localtime(value).strftime("%d %b %H:%M")


def parse_due_date(raw, status: str) -> tuple[str, bool]:
    if not raw:
        return "", False
    if hasattr(raw, "strftime") and not hasattr(raw, "hour"):
        human = raw.strftime("%d %b %Y")
        if status == ChatTask.Status.DONE:
            return human, False
        return human, raw < timezone.localdate()
    try:
        parsed = timezone.datetime.fromisoformat(str(raw))
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    except ValueError:
        return str(raw), False
    parsed_local = timezone.localtime(parsed)
    human = parsed_local.strftime("%d %b %Y")
    if status == ChatTask.Status.DONE:
        return human, False
    today = timezone.localdate()
    return human, parsed_local.date() < today


def option_label(options: Sequence[tuple[str, str]], value: str, fallback: str) -> str:
    for candidate, label in options:
        if candidate == value:
            return label
    return fallback or value


TASK_STATUS_OPTIONS: list[tuple[str, str]] = list(ChatTask.Status.choices)
TASK_PRIORITY_OPTIONS: list[tuple[str, str]] = list(ChatTask.Priority.choices)
VALID_TASK_STATUSES = {choice[0] for choice in TASK_STATUS_OPTIONS}
VALID_TASK_PRIORITIES = {choice[0] for choice in TASK_PRIORITY_OPTIONS}


def sanitize_task_filter(filter_: TaskFilter) -> TaskFilter:
    status = (filter_.status or "").strip().lower()
    priority = (filter_.priority or "").strip().lower()
    query = (filter_.query or "").strip()
    if status not in VALID_TASK_STATUSES:
        status = ""
    if priority not in VALID_TASK_PRIORITIES:
        priority = ""
    return TaskFilter(status=status, priority=priority, query=query)


def matches_task_filter(task: ChatTask, filter_: TaskFilter) -> bool:
    if filter_.status and task.status != filter_.status:
        return False
    if filter_.priority and task.priority != filter_.priority:
        return False
    if filter_.query:
        needle = filter_.query.lower()
        haystacks = [task.title.lower(), task.description.lower(), (task.assigned_to.display_name.lower() if task.assigned_to else "")]
        return any(needle in hay for hay in haystacks)
    return True


def count_todos(items: Iterable[ChatTaskItem]) -> tuple[int, int]:
    outstanding = 0
    completed = 0
    for item in items:
        if item.is_done:
            completed += 1
        else:
            outstanding += 1
    return outstanding, completed


def task_summary(tasks: Iterable[ChatTask]) -> TaskSummary:
    summary = TaskSummary()
    for task in tasks:
        summary.total += 1
        match task.status:
            case ChatTask.Status.TODO:
                summary.todo += 1
            case ChatTask.Status.IN_PROGRESS:
                summary.in_progress += 1
            case ChatTask.Status.BLOCKED:
                summary.blocked += 1
            case ChatTask.Status.DONE:
                summary.done += 1
        match task.priority:
            case ChatTask.Priority.URGENT:
                summary.urgent += 1
            case ChatTask.Priority.HIGH:
                summary.high += 1
            case ChatTask.Priority.MEDIUM:
                summary.medium += 1
            case ChatTask.Priority.LOW:
                summary.low += 1
    return summary


def ensure_system_chat_message(messages: list[ChatMessageDTO], body: str) -> list[ChatMessageDTO]:
    trimmed = body.strip()
    if not trimmed:
        return messages
    if messages and messages[0].author_id == 0 and messages[0].author_name.lower() == "system" and messages[0].body == trimmed:
        return messages
    system_message = ChatMessageDTO(
        id=0,
        author_id=0,
        author_name="System",
        body=trimmed,
        created_at_human=humanize_timestamp(timezone.now()),
        is_mine=False,
    )
    return [system_message, *messages]


def messages_for_admin(user) -> list[ChatMessageDTO]:
    messages = []
    for message in ChatMessage.objects.select_related("author").order_by("created_at", "id"):
        messages.append(
            ChatMessageDTO(
                id=message.id,
                author_id=message.author_id,
                author_name=message.author.display_name,
                body=message.body,
                created_at_human=humanize_timestamp(message.created_at),
                is_mine=user and message.author_id == user.id,
            )
        )
    return messages


def task_items_to_dto(items: Iterable[ChatTaskItem]) -> list[ChatTaskItemDTO]:
    return [
        ChatTaskItemDTO(
            id=item.id,
            label=item.label,
            is_done=item.is_done,
            created_at_human=humanize_timestamp(item.created_at),
        )
        for item in items
    ]


def task_to_dto(task: ChatTask) -> ChatTaskDTO:
    assigned_to_name = task.assigned_to.display_name if task.assigned_to else "Unassigned"
    has_assignee = task.assigned_to is not None
    assigned_to_value = task.assigned_to_id or 0
    due_date_human, is_overdue = parse_due_date(task.due_date, task.status)
    todo_items = list(task.todos.all())
    outstanding, completed = count_todos(todo_items)
    return ChatTaskDTO(
        id=task.id,
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        due_date=task.due_date.isoformat() if task.due_date else "",
        created_at_human=humanize_timestamp(task.created_at),
        updated_at_human=humanize_timestamp(task.updated_at),
        status_label=option_label(TASK_STATUS_OPTIONS, task.status, task.get_status_display()),
        priority_label=option_label(TASK_PRIORITY_OPTIONS, task.priority, task.get_priority_display()),
        assigned_to_id=task.assigned_to_id,
        assigned_to_name=assigned_to_name,
        has_assignee=has_assignee,
        assigned_to_value=assigned_to_value,
        due_date_human=due_date_human,
        is_overdue=is_overdue,
        outstanding_todos=outstanding,
        completed_todos=completed,
        todos=task_items_to_dto(todo_items),
    )


def tasks_for_admin(filter_: TaskFilter) -> tuple[list[ChatTaskDTO], TaskSummary]:
    tasks_qs = ChatTask.objects.select_related("assigned_to", "created_by").prefetch_related("todos")
    sanitized = sanitize_task_filter(filter_)
    if sanitized.status:
        tasks_qs = tasks_qs.filter(status=sanitized.status)
    if sanitized.priority:
        tasks_qs = tasks_qs.filter(priority=sanitized.priority)
    if sanitized.query:
        needle = sanitized.query
        tasks_qs = tasks_qs.filter(
            Q(title__icontains=needle)
            | Q(description__icontains=needle)
            | Q(assigned_to__full_name__icontains=needle)
            | Q(assigned_to__username__icontains=needle)
        )
    tasks_qs = tasks_qs.order_by(
        Case(When(status=ChatTask.Status.DONE, then=Value(1)), default=Value(0), output_field=IntegerField()),
        Case(
            When(priority=ChatTask.Priority.URGENT, then=Value(0)),
            When(priority=ChatTask.Priority.HIGH, then=Value(1)),
            When(priority=ChatTask.Priority.MEDIUM, then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        ),
        Coalesce("due_date", Value("9999-12-31")),
        "-created_at",
    )
    tasks = list(tasks_qs)
    summary = task_summary(ChatTask.objects.all())
    dtos = [task_to_dto(task) for task in tasks]
    return dtos, summary


def committees_for_context():
    return COMMITTEES


def posts_by_committee() -> dict[str, list[Post]]:
    return {"Posts": list(Post.objects.all())}


def videos_by_category() -> dict[str, list[Video]]:
    return {"Videos": list(Video.objects.all())}


__all__ = [
    "TaskFilter",
    "TaskSummary",
    "ChatMessageDTO",
    "ChatTaskDTO",
    "ChatTaskItemDTO",
    "TASK_STATUS_OPTIONS",
    "TASK_PRIORITY_OPTIONS",
    "messages_for_admin",
    "ensure_system_chat_message",
    "tasks_for_admin",
    "committees_for_context",
    "posts_by_committee",
    "videos_by_category",
    "normalize_committee_key",
    "committee_by_key",
]

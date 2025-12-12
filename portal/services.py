from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from django.contrib.auth import get_user_model
from django.db.models import Case, IntegerField, Q, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.html import escape
from django.utils.safestring import mark_safe

from .constants import COMMITTEES, committee_by_key, normalize_committee_key
from .models import ChatMessage, ChatTask, ChatTaskItem, Media, Post, Video

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


# ─────────────────────────────────────────────────────────────────────────────
# Post Content Rendering (Markdown-like + HTML)
# ─────────────────────────────────────────────────────────────────────────────

def extract_media_from_content(content: str) -> list[dict]:
    """Extract image and video URLs from post content"""
    media_items = []
    
    # Markdown image pattern: ![alt](url)
    md_images = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', content)
    for alt, url in md_images:
        media_items.append({
            "url": url.strip(),
            "title": alt.strip() or "",
            "media_type": "image"
        })
    
    # HTML img pattern: <img src="url" ...>
    html_images = re.findall(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', content, re.IGNORECASE)
    for url in html_images:
        media_items.append({
            "url": url.strip(),
            "title": "",
            "media_type": "image"
        })
    
    # Markdown video/embed pattern: [video](url) or special syntax
    # YouTube/Vimeo embedded links
    video_patterns = [
        r'\[video\]\(([^)]+)\)',
        r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]+)',
        r'(?:https?://)?(?:www\.)?vimeo\.com/(\d+)',
    ]
    
    for pattern in video_patterns:
        matches = re.findall(pattern, content)
        for match in matches:
            url = match if match.startswith('http') else f"https://youtube.com/watch?v={match}"
            media_items.append({
                "url": url,
                "title": "",
                "media_type": "video"
            })
    
    # HTML video/iframe patterns
    html_videos = re.findall(r'<(?:video|iframe)[^>]+src=["\']([^"\']+)["\'][^>]*>', content, re.IGNORECASE)
    for url in html_videos:
        media_items.append({
            "url": url.strip(),
            "title": "",
            "media_type": "video"
        })
    
    return media_items


def sync_post_media(post: Post) -> None:
    """Extract media from post content and sync with Media model"""
    # Remove existing media links for this post
    Media.objects.filter(post=post).delete()
    
    # Extract and create new media entries
    media_items = extract_media_from_content(post.content)
    
    # Also include thumbnail if present
    if post.thumbnail:
        media_items.insert(0, {
            "url": post.thumbnail,
            "title": f"Thumbnail: {post.title}",
            "media_type": "image"
        })
    
    # Create Media objects, avoiding duplicates
    seen_urls = set()
    for item in media_items:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            Media.objects.create(
                url=item["url"],
                title=item["title"],
                media_type=item["media_type"],
                post=post
            )


def render_post_content(content: str) -> str:
    """
    Render post content from Markdown-like syntax to HTML.
    Supports: headings, bold, italic, underline, code blocks, lists, images, videos, links.
    """
    # Work with a copy
    html = content
    
    # Escape HTML special chars first (but preserve intentional HTML)
    # We'll process markdown then allow specific HTML tags
    
    # Code blocks (```code```) - preserve and highlight
    def code_block_replace(match):
        lang = match.group(1) or ""
        code = escape(match.group(2))
        return f'<pre class="code-block bg-sage-100 dark:bg-sage-800 rounded-xl p-4 overflow-x-auto my-4"><code class="text-sm font-mono text-sage-800 dark:text-cream-100" data-lang="{lang}">{code}</code></pre>'
    
    html = re.sub(r'```(\w*)\n?([\s\S]*?)```', code_block_replace, html)
    
    # Inline code (`code`)
    html = re.sub(r'`([^`]+)`', r'<code class="bg-sage-100 dark:bg-sage-800 px-2 py-0.5 rounded text-sm font-mono">\1</code>', html)
    
    # Headings
    html = re.sub(r'^### (.+)$', r'<h3 class="text-xl font-serif font-semibold text-sage-800 dark:text-cream-100 mt-6 mb-3">\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2 class="text-2xl font-serif font-semibold text-sage-800 dark:text-cream-100 mt-8 mb-4">\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<h1 class="text-3xl font-serif font-bold text-sage-800 dark:text-cream-100 mt-8 mb-4">\1</h1>', html, flags=re.MULTILINE)
    
    # Bold, Italic, Underline
    html = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', html)
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'__(.+?)__', r'<u>\1</u>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    html = re.sub(r'_(.+?)_', r'<em>\1</em>', html)
    
    # Images: ![alt](url)
    def img_replace(match):
        alt = match.group(1)
        url = match.group(2)
        return f'<figure class="my-6"><img src="{url}" alt="{alt}" class="rounded-2xl shadow-lg max-w-full h-auto mx-auto" loading="lazy">{f"<figcaption class=text-center text-sm text-sage-500 dark:text-sage-400 mt-2>{alt}</figcaption>" if alt else ""}</figure>'
    
    html = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', img_replace, html)
    
    # Links: [text](url)
    html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" class="text-sage-600 dark:text-cream-300 underline hover:text-sage-800 dark:hover:text-cream-100 transition-colors">\1</a>', html)
    
    # YouTube embeds
    def youtube_embed(match):
        video_id = match.group(1)
        return f'<div class="relative w-full aspect-video my-6"><iframe src="https://www.youtube.com/embed/{video_id}" class="absolute inset-0 w-full h-full rounded-2xl shadow-lg" frameborder="0" allowfullscreen loading="lazy"></iframe></div>'
    
    html = re.sub(r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]+)', youtube_embed, html)
    
    # Unordered lists
    def process_ul(text):
        lines = text.split('\n')
        result = []
        in_list = False
        for line in lines:
            if re.match(r'^[\-\*] ', line):
                if not in_list:
                    result.append('<ul class="list-disc list-inside space-y-2 my-4 ml-4">')
                    in_list = True
                item = re.sub(r'^[\-\*] ', '', line)
                result.append(f'<li class="text-sage-700 dark:text-cream-200">{item}</li>')
            else:
                if in_list:
                    result.append('</ul>')
                    in_list = False
                result.append(line)
        if in_list:
            result.append('</ul>')
        return '\n'.join(result)
    
    html = process_ul(html)
    
    # Ordered lists
    def process_ol(text):
        lines = text.split('\n')
        result = []
        in_list = False
        for line in lines:
            if re.match(r'^\d+\. ', line):
                if not in_list:
                    result.append('<ol class="list-decimal list-inside space-y-2 my-4 ml-4">')
                    in_list = True
                item = re.sub(r'^\d+\. ', '', line)
                result.append(f'<li class="text-sage-700 dark:text-cream-200">{item}</li>')
            else:
                if in_list:
                    result.append('</ol>')
                    in_list = False
                result.append(line)
        if in_list:
            result.append('</ol>')
        return '\n'.join(result)
    
    html = process_ol(html)
    
    # Horizontal rule
    html = re.sub(r'^---+$', r'<hr class="my-8 border-sage-200 dark:border-sage-700">', html, flags=re.MULTILINE)
    
    # Blockquotes
    def process_blockquotes(text):
        lines = text.split('\n')
        result = []
        in_quote = False
        for line in lines:
            if line.startswith('> '):
                if not in_quote:
                    result.append('<blockquote class="border-l-4 border-sage-400 dark:border-sage-600 pl-4 py-2 my-4 italic text-sage-600 dark:text-sage-300">')
                    in_quote = True
                result.append(line[2:])
            else:
                if in_quote:
                    result.append('</blockquote>')
                    in_quote = False
                result.append(line)
        if in_quote:
            result.append('</blockquote>')
        return '\n'.join(result)
    
    html = process_blockquotes(html)
    
    # Paragraphs - wrap remaining text blocks
    paragraphs = html.split('\n\n')
    processed = []
    for p in paragraphs:
        p = p.strip()
        if p and not p.startswith('<'):
            # Wrap plain text in paragraph tags
            lines = p.split('\n')
            wrapped_lines = []
            for line in lines:
                if line.strip() and not line.strip().startswith('<'):
                    wrapped_lines.append(f'<p class="text-sage-700 dark:text-cream-200 leading-relaxed mb-4">{line}</p>')
                else:
                    wrapped_lines.append(line)
            processed.append('\n'.join(wrapped_lines))
        else:
            processed.append(p)
    
    html = '\n\n'.join(processed)
    
    return mark_safe(html)


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
    "extract_media_from_content",
    "sync_post_media",
    "render_post_content",
]

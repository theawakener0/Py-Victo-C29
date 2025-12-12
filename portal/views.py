from __future__ import annotations

import queue
import re
import time
from functools import wraps
from typing import Callable

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from . import services
from .forms import (
    ChatMessageForm,
    ChatTaskAssignmentForm,
    ChatTaskForm,
    ChatTaskStatusForm,
    ChatTaskTodoForm,
    LoginForm,
    MediaFilterForm,
    PostForm,
    SignupForm,
    VideoForm,
)
from .models import AccountUser, ChatMessage, ChatTask, ChatTaskItem, Media, Post, Video
from .services import (
    MAX_CHAT_MESSAGE_LENGTH,
    MAX_TASK_DESCRIPTION_LENGTH,
    MAX_TASK_TITLE_LENGTH,
    MAX_TODO_LABEL_LENGTH,
    TASK_PRIORITY_OPTIONS,
    TASK_STATUS_OPTIONS,
    TaskFilter,
    ensure_system_chat_message,
    extract_media_from_content,
    messages_for_admin,
    posts_by_committee,
    sanitize_task_filter,
    tasks_for_admin,
    videos_by_category,
)
from .sse import admin_event_hub, format_event, heartbeat_event

ADMIN_CHAT_SYSTEM_MESSAGE = "Executive Coordination Hub ready. Log action items and updates here."
LANDING_CHAT_SYSTEM_MESSAGE = "Welcome to the Executive Coordination Hub. Use /task create to open a new task, /todo to add checklist items."


def is_htmx(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


def admin_required(view_func: Callable) -> Callable:
    @login_required
    @user_passes_test(lambda u: u.is_staff, login_url="login")
    @wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return wrapper


def task_publisher_required(view_func: Callable) -> Callable:
    """Decorator for views that require task publishing permission (union_president, union_vice_president)"""
    @login_required
    @user_passes_test(lambda u: u.is_staff and u.can_publish_tasks, login_url="login")
    @wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return wrapper


def media_publisher_required(view_func: Callable) -> Callable:
    """Decorator for views that require media publishing permission (media_admin_01, media_admin_02)"""
    @login_required
    @user_passes_test(lambda u: u.is_staff and u.can_publish_media, login_url="login")
    @wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return wrapper


def build_admin_hub_data(request: HttpRequest, filter_: TaskFilter, system_message: str = "") -> dict:
    sanitized = sanitize_task_filter(filter_)
    user = request.user if request.user.is_authenticated else None
    message_dtos = messages_for_admin(user)
    if system_message:
        message_dtos = ensure_system_chat_message(message_dtos, system_message)
    task_dtos, summary = tasks_for_admin(sanitized)
    admin_users = (
        AccountUser.objects.filter(is_staff=True)
        .order_by("full_name", "username")
        .values("id", "username", "full_name")
    )

    return {
        "messages": message_dtos,
        "tasks": task_dtos,
        "admin_users": list(admin_users),
        "task_summary": summary,
        "task_filter": sanitized,
        "task_status_options": [
            {"value": value, "label": label} for value, label in TASK_STATUS_OPTIONS
        ],
        "task_priority_options": [
            {"value": value, "label": label} for value, label in TASK_PRIORITY_OPTIONS
        ],
    }


def base_context(request: HttpRequest) -> dict:
    user = request.user
    is_auth = user.is_authenticated
    return {
        "is_auth": is_auth,
        "is_admin": user.is_staff if is_auth else False,
        "can_publish_tasks": user.can_publish_tasks if is_auth else False,
        "can_publish_media": user.can_publish_media if is_auth else False,
        "current_user_id": user.id if is_auth else 0,
        "current_user_name": user.get_username() if is_auth else "",
        "committees": services.COMMITTEES,
    }


@require_GET
def home(request: HttpRequest) -> HttpResponse:
    context = base_context(request)
    context["posts"] = posts_by_committee()
    context["videos"] = videos_by_category()

    if request.user.is_authenticated and request.user.is_staff:
        context["admin_hub"] = build_admin_hub_data(request, TaskFilter(), LANDING_CHAT_SYSTEM_MESSAGE)

    return render(request, "home.html", context)


@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            if is_htmx(request):
                response = HttpResponse(status=204)
                response["HX-Redirect"] = "/"
                return response
            return redirect("home")
    else:
        form = LoginForm(request)
    context = base_context(request)
    context["form"] = form
    return render(request, "account/login.html", context)


@require_http_methods(["GET", "POST"])
def signup_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            if is_htmx(request):
                response = HttpResponse(status=204)
                response["HX-Redirect"] = "/"
                return response
            return redirect("home")
    else:
        form = SignupForm()
    context = base_context(request)
    context["form"] = form
    return render(request, "account/signup.html", context)


@login_required
@require_http_methods(["POST"])
def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    response = redirect("login")
    response["HX-Redirect"] = "/login.html"
    return response


@login_required
@require_GET
def posts_list(request: HttpRequest) -> HttpResponse:
    context = base_context(request)
    posts = Post.objects.all()
    
    # Handle htmx partial loading
    if is_htmx(request):
        return render(request, "posts/partials/post_list.html", {"posts": posts, **context})
    
    context["posts"] = posts
    return render(request, "posts/list.html", context)


@require_GET
def post_detail(request: HttpRequest, slug: str) -> HttpResponse:
    post = get_object_or_404(Post, slug=slug)
    context = base_context(request)
    context["post"] = post
    context["rendered_content"] = services.render_post_content(post.content)
    
    # Handle htmx partial loading
    if is_htmx(request):
        return render(request, "posts/partials/post_content.html", context)
    
    return render(request, "posts/detail.html", context)


@media_publisher_required
@require_http_methods(["GET", "POST"])
def create_post(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = PostForm(request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.committee = services.normalize_committee_key(post.committee)
            post.save()
            # Extract and save media from content
            services.sync_post_media(post)
            messages.success(request, "Post created")
            if is_htmx(request):
                response = HttpResponse(status=204)
                response["HX-Redirect"] = f"/posts/{post.slug}"
                return response
            return redirect("post_detail", slug=post.slug)
    else:
        form = PostForm()
    context = base_context(request)
    context["form"] = form
    return render(request, "posts/create.html", context)


@media_publisher_required
@require_http_methods(["GET", "POST"])
def edit_post(request: HttpRequest, pk: int) -> HttpResponse:
    post = get_object_or_404(Post, pk=pk)
    if request.method == "POST":
        form = PostForm(request.POST, instance=post)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.committee = services.normalize_committee_key(updated.committee)
            updated.save()
            # Re-sync media from updated content
            services.sync_post_media(updated)
            messages.success(request, "Post updated")
            if is_htmx(request):
                response = HttpResponse(status=204)
                response["HX-Redirect"] = f"/posts/{updated.slug}"
                return response
            return redirect("post_detail", slug=updated.slug)
    else:
        form = PostForm(instance=post)
    context = base_context(request)
    context["form"] = form
    context["post"] = post
    return render(request, "posts/edit.html", context)


@media_publisher_required
@require_http_methods(["POST"])
def delete_post(request: HttpRequest, pk: int) -> HttpResponse:
    post = get_object_or_404(Post, pk=pk)
    post.delete()
    messages.success(request, "Post deleted")
    return redirect("posts")


@login_required
@require_GET
def videos_list(request: HttpRequest) -> HttpResponse:
    context = base_context(request)
    context["posts"] = posts_by_committee()
    context["videos"] = videos_by_category()
    return render(request, "videos/list.html", context)


@media_publisher_required
@require_http_methods(["GET", "POST"])
def create_video(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = VideoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Video created")
            return redirect("videos")
    else:
        form = VideoForm()
    context = base_context(request)
    context["form"] = form
    return render(request, "videos/create.html", context)


@media_publisher_required
@require_http_methods(["GET", "POST"])
def edit_video(request: HttpRequest, pk: int) -> HttpResponse:
    video = get_object_or_404(Video, pk=pk)
    if request.method == "POST":
        form = VideoForm(request.POST, instance=video)
        if form.is_valid():
            form.save()
            messages.success(request, "Video updated")
            return redirect("videos")
    else:
        form = VideoForm(instance=video)
    context = base_context(request)
    context["form"] = form
    context["video"] = video
    return render(request, "videos/edit.html", context)


@media_publisher_required
@require_http_methods(["POST"])
def delete_video(request: HttpRequest, pk: int) -> HttpResponse:
    video = get_object_or_404(Video, pk=pk)
    video.delete()
    messages.success(request, "Video deleted")
    return redirect("videos")


@require_GET
def legacy_view(request: HttpRequest) -> HttpResponse:
    context = base_context(request)
    return render(request, "legacy.html", context)


# ─────────────────────────────────────────────────────────────────────────────
# Media Gallery Views
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_GET
def media_list(request: HttpRequest) -> HttpResponse:
    """Media gallery page with htmx filtering"""
    context = base_context(request)
    media_type = request.GET.get("media_type", "")
    search = request.GET.get("search", "")
    
    media_qs = Media.objects.select_related("post")
    
    if media_type:
        media_qs = media_qs.filter(media_type=media_type)
    if search:
        media_qs = media_qs.filter(title__icontains=search)
    
    context["media_items"] = media_qs
    context["filter_form"] = MediaFilterForm(initial={"media_type": media_type, "search": search})
    context["current_filter"] = media_type
    context["current_search"] = search
    
    # Handle htmx partial loading for filtering
    if is_htmx(request):
        return render(request, "media/partials/media_grid.html", context)
    
    return render(request, "media/list.html", context)


@require_GET
def post_editor_help(request: HttpRequest) -> HttpResponse:
    """Return the formatting help dialog content"""
    return render(request, "posts/partials/editor_help.html")


@require_http_methods(["POST"])
def preview_post_content(request: HttpRequest) -> HttpResponse:
    """Preview rendered post content via htmx"""
    content = request.POST.get("content", "")
    rendered = services.render_post_content(content)
    return HttpResponse(rendered)


@require_GET
def committee_view(request: HttpRequest, key: str) -> HttpResponse:
    committee = services.committee_by_key(key)
    if not committee:
        return HttpResponse(status=404)
    posts = posts_by_committee()["Posts"]
    filtered = [post for post in posts if services.normalize_committee_key(post.committee) == committee.key]
    context = base_context(request)
    context.update(
        {
            "committee": committee,
            "committee_posts": filtered,
            "posts": {"Posts": posts},
        }
    )
    return render(request, "committees/detail.html", context)


def _task_filter_from_request(request: HttpRequest) -> TaskFilter:
    return TaskFilter(
        status=request.GET.get("status", ""),
        priority=request.GET.get("priority", ""),
        query=request.GET.get("q", ""),
    )


def _render_chat_fragment(request: HttpRequest, *, system_message: str = ADMIN_CHAT_SYSTEM_MESSAGE) -> HttpResponse:
    context = base_context(request)
    context["admin_hub"] = build_admin_hub_data(request, _task_filter_from_request(request), system_message)
    return render(request, "admin/hub/partials/chat.html", context)


def _render_tasks_fragment(request: HttpRequest) -> HttpResponse:
    context = base_context(request)
    context["admin_hub"] = build_admin_hub_data(request, _task_filter_from_request(request))
    return render(request, "admin/hub/partials/tasks.html", context)


@admin_required
@require_GET
def admin_hub(request: HttpRequest) -> HttpResponse:
    context = base_context(request)
    context["admin_hub"] = build_admin_hub_data(request, _task_filter_from_request(request), ADMIN_CHAT_SYSTEM_MESSAGE)
    return render(request, "admin/hub/index.html", context)


@admin_required
@require_GET
def admin_hub_chat_fragment(request: HttpRequest) -> HttpResponse:
    return _render_chat_fragment(request)


@admin_required
@require_GET
def admin_hub_tasks_fragment(request: HttpRequest) -> HttpResponse:
    return _render_tasks_fragment(request)


@admin_required
@require_http_methods(["POST"])
def create_chat_message(request: HttpRequest) -> HttpResponse:
    form = ChatMessageForm(request.POST)
    if form.is_valid():
        body = form.cleaned_data["body"][:MAX_CHAT_MESSAGE_LENGTH]
        ChatMessage.objects.create(author=request.user, body=body)
        admin_event_hub.broadcast(format_event("chat", str(int(time.time_ns()))))
        if is_htmx(request):
            return _render_chat_fragment(request)
        return redirect("admin_hub")
    return HttpResponseBadRequest("Invalid message")


@admin_required
@require_http_methods(["POST"])
def delete_chat_message(request: HttpRequest, pk: int) -> HttpResponse:
    message = get_object_or_404(ChatMessage, pk=pk)
    message.delete()
    admin_event_hub.broadcast(format_event("chat", str(int(time.time_ns()))))
    if is_htmx(request):
        return _render_chat_fragment(request)
    return redirect("admin_hub")


@task_publisher_required
@require_http_methods(["POST"])
def create_chat_task(request: HttpRequest) -> HttpResponse:
    form = ChatTaskForm(request.POST)
    if form.is_valid():
        task = form.save(commit=False)
        task.title = task.title[:MAX_TASK_TITLE_LENGTH]
        task.description = task.description[:MAX_TASK_DESCRIPTION_LENGTH]
        task.created_by = request.user
        task.save()
        form.save_m2m()
        admin_event_hub.broadcast(format_event("tasks", str(int(time.time_ns()))))
        if is_htmx(request):
            return _render_tasks_fragment(request)
        return redirect("admin_hub")
    return HttpResponseBadRequest("Invalid task")


@admin_required
@require_http_methods(["POST"])
def update_task_status(request: HttpRequest, pk: int) -> HttpResponse:
    task = get_object_or_404(ChatTask, pk=pk)
    form = ChatTaskStatusForm(request.POST, instance=task)
    if form.is_valid():
        form.save()
        admin_event_hub.broadcast(format_event("tasks", str(int(time.time_ns()))))
        if is_htmx(request):
            return _render_tasks_fragment(request)
        return redirect("admin_hub")
    return HttpResponseBadRequest("Invalid status")


@admin_required
@require_http_methods(["POST"])
def update_task_assignment(request: HttpRequest, pk: int) -> HttpResponse:
    task = get_object_or_404(ChatTask, pk=pk)
    form = ChatTaskAssignmentForm(request.POST, instance=task)
    if form.is_valid():
        form.save()
        admin_event_hub.broadcast(format_event("tasks", str(int(time.time_ns()))))
        if is_htmx(request):
            return _render_tasks_fragment(request)
        return redirect("admin_hub")
    return HttpResponseBadRequest("Invalid assignment")


@admin_required
@require_http_methods(["POST"])
def add_task_todo(request: HttpRequest, pk: int) -> HttpResponse:
    task = get_object_or_404(ChatTask, pk=pk)
    form = ChatTaskTodoForm(request.POST)
    if form.is_valid():
        todo = form.save(commit=False)
        todo.label = todo.label[:MAX_TODO_LABEL_LENGTH]
        todo.task = task
        todo.save()
        admin_event_hub.broadcast(format_event("tasks", str(int(time.time_ns()))))
        if is_htmx(request):
            return _render_tasks_fragment(request)
        return redirect("admin_hub")
    return HttpResponseBadRequest("Invalid todo")


@task_publisher_required
@require_http_methods(["POST"])
def delete_task(request: HttpRequest, pk: int) -> HttpResponse:
    task = get_object_or_404(ChatTask, pk=pk)
    task.delete()
    admin_event_hub.broadcast(format_event("tasks", str(int(time.time_ns()))))
    if is_htmx(request):
        return _render_tasks_fragment(request)
    return redirect("admin_hub")


@admin_required
@require_http_methods(["POST"])
def toggle_todo(request: HttpRequest, pk: int) -> HttpResponse:
    todo = get_object_or_404(ChatTaskItem, pk=pk)
    mark_done = request.POST.get("is_done") in {"1", "true", "True", "on"}
    todo.is_done = mark_done
    todo.save(update_fields=["is_done"])
    admin_event_hub.broadcast(format_event("tasks", str(int(time.time_ns()))))
    if is_htmx(request):
        return _render_tasks_fragment(request)
    return redirect("admin_hub")


@admin_required
@require_GET
def admin_chat_stream(request: HttpRequest) -> StreamingHttpResponse:
    channel = admin_event_hub.register()

    def event_stream():
        yield heartbeat_event()
        try:
            while True:
                try:
                    event = channel.get(timeout=30)
                except queue.Empty:
                    event = heartbeat_event()
                yield event
        finally:
            admin_event_hub.unregister(channel)

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response

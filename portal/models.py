from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from .constants import committee_by_key


class AccountUser(AbstractUser):
    full_name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=32, blank=True)

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"

    @property
    def display_name(self) -> str:
        if self.full_name:
            return self.full_name.strip()
        name = self.get_full_name().strip()
        return name or self.username

    @property
    def is_admin(self) -> bool:  # parity with the Go implementation
        return self.is_staff


class Post(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    date = models.DateField(default=timezone.now)
    committee = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self) -> str:
        return self.title

    @property
    def committee_label(self) -> str:
        if not self.committee:
            return ""
        committee = committee_by_key(self.committee)
        if committee:
            return committee.name
        return self.committee.replace("-", " ").replace("_", " ").title()


class Video(models.Model):
    title = models.CharField(max_length=200)
    url = models.URLField()
    image = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return self.title


class ChatMessage(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_messages")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.author.display_name}: {self.body[:24]}"


class ChatTask(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "To Do"
        IN_PROGRESS = "in_progress", "In Progress"
        BLOCKED = "blocked", "Blocked"
        DONE = "done", "Done"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.TODO)
    priority = models.CharField(max_length=32, choices=Priority.choices, default=Priority.MEDIUM)
    due_date = models.DateField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name="created_tasks")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="assigned_tasks", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "priority", "due_date", "-created_at"]

    def __str__(self) -> str:
        return self.title

    def outstanding_todos(self) -> int:
        return self.todos.filter(is_done=False).count()

    def completed_todos(self) -> int:
        return self.todos.filter(is_done=True).count()


class ChatTaskItem(models.Model):
    task = models.ForeignKey(ChatTask, on_delete=models.CASCADE, related_name="todos")
    label = models.CharField(max_length=500)
    is_done = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.label

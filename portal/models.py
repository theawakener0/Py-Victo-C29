from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from .constants import committee_by_key


class AccountUser(AbstractUser):
    class AdminRole(models.TextChoices):
        NONE = "none", "No Admin Role"
        UNION_PRESIDENT = "union_president", "Union President"
        UNION_VICE_PRESIDENT = "union_vice_president", "Union Vice President"
        MEDIA_ADMIN = "media_admin", "Media Admin"
        OPERATIONS_ADMIN = "operations_admin", "Operations Admin"
        COMMITTEE_LEAD = "committee_lead", "Committee Lead"
        DEV_ADMIN = "dev_admin", "Development Admin"

    full_name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    admin_role = models.CharField(
        max_length=32,
        choices=AdminRole.choices,
        default=AdminRole.NONE,
        blank=True,
    )

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"

    # Roles that can publish tasks
    TASK_PUBLISHER_ROLES = {
        AdminRole.UNION_PRESIDENT,
        AdminRole.UNION_VICE_PRESIDENT,
    }

    # Roles that can publish posts and media
    MEDIA_PUBLISHER_ROLES = {
        AdminRole.UNION_PRESIDENT,
        AdminRole.UNION_VICE_PRESIDENT,
        AdminRole.MEDIA_ADMIN,
    }

    @property
    def display_name(self) -> str:
        if self.full_name:
            return self.full_name.strip()
        name = self.get_full_name().strip()
        return name or self.username

    @property
    def is_admin(self) -> bool:  # parity with the Go implementation
        return self.is_staff

    @property
    def can_publish_tasks(self) -> bool:
        """Check if user can create/delete tasks (union_president, union_vice_president only)"""
        return self.is_staff and self.admin_role in self.TASK_PUBLISHER_ROLES

    @property
    def can_publish_media(self) -> bool:
        """Check if user can create/edit/delete posts and videos (media_admin only)"""
        return self.is_staff and self.admin_role in self.MEDIA_PUBLISHER_ROLES


class Post(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    excerpt = models.TextField(max_length=500, blank=True, help_text="Short preview text (auto-generated if empty)")
    content = models.TextField(help_text="Supports Markdown/HTML formatting")
    thumbnail = models.URLField(blank=True, help_text="Optional thumbnail image URL")
    date = models.DateField(default=timezone.now)
    committee = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        from django.utils.text import slugify
        import re
        if not self.slug:
            base_slug = slugify(self.title)[:200]
            slug = base_slug
            counter = 1
            while Post.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        if not self.excerpt:
            # Strip HTML/Markdown and get first 300 chars
            text = re.sub(r'<[^>]+>', '', self.content)
            text = re.sub(r'[#*_`\[\]!]', '', text)
            self.excerpt = text[:300].strip() + ('...' if len(text) > 300 else '')
        super().save(*args, **kwargs)

    @property
    def committee_label(self) -> str:
        if not self.committee:
            return ""
        committee = committee_by_key(self.committee)
        if committee:
            return committee.name
        return self.committee.replace("-", " ").replace("_", " ").title()

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('post_detail', kwargs={'slug': self.slug})


class Video(models.Model):
    title = models.CharField(max_length=200)
    url = models.URLField()
    image = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return self.title


class Media(models.Model):
    """Media files extracted from posts or uploaded directly"""
    class MediaType(models.TextChoices):
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"

    title = models.CharField(max_length=200, blank=True)
    url = models.URLField()
    media_type = models.CharField(max_length=16, choices=MediaType.choices, default=MediaType.IMAGE)
    post = models.ForeignKey(Post, on_delete=models.SET_NULL, null=True, blank=True, related_name="media_items")
    thumbnail = models.URLField(blank=True, help_text="Thumbnail for videos")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "media"

    def __str__(self) -> str:
        return self.title or self.url


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

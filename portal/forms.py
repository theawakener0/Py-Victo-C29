from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import AccountUser, ChatMessage, ChatTask, ChatTaskItem, Media, Post, Video


# Pure Dark Theme Form Classes - High Contrast for Better Readability
INPUT_CLASS = (
    "w-full rounded-xl border border-white/10 bg-black/90 text-gray-100 "
    "placeholder-gray-500 px-4 py-3.5 transition-all duration-200 "
    "focus:border-gray-500 focus:ring-2 focus:ring-gray-500/20 focus:outline-none"
)

TEXTAREA_CLASS = INPUT_CLASS + " min-h-[9rem] resize-y"

# Content Editor - Black background with soft white text for comfortable writing
CONTENT_EDITOR_CLASS = (
    "w-full rounded-xl border border-white/10 bg-black text-gray-200 "
    "placeholder-gray-600 px-5 py-4 font-mono text-sm leading-relaxed "
    "min-h-[28rem] resize-y transition-all duration-200 "
    "focus:border-gray-500 focus:ring-2 focus:ring-gray-500/20 focus:outline-none"
)


class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={"autofocus": True, "class": INPUT_CLASS}))
    password = forms.CharField(strip=False, widget=forms.PasswordInput(attrs={"class": INPUT_CLASS}))


class SignupForm(UserCreationForm):
    full_name = forms.CharField(max_length=255)
    phone = forms.CharField(max_length=32)

    class Meta(UserCreationForm.Meta):
        model = AccountUser
        fields = ("username", "full_name", "phone")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.copy()
            existing["class"] = INPUT_CLASS
            field.widget.attrs = existing

    def save(self, commit: bool = True) -> AccountUser:
        user = super().save(commit=False)
        user.full_name = self.cleaned_data["full_name"].strip()
        user.phone = self.cleaned_data["phone"].strip()
        if commit:
            user.save()
        return user


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ("title", "thumbnail", "excerpt", "content", "committee")
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Post title"}),
            "thumbnail": forms.URLInput(attrs={"class": INPUT_CLASS, "placeholder": "https://example.com/image.jpg (optional)"}),
            "excerpt": forms.Textarea(attrs={"class": TEXTAREA_CLASS, "rows": 2, "placeholder": "Short preview text (auto-generated if empty)"}),
            "content": forms.Textarea(attrs={
                "class": CONTENT_EDITOR_CLASS, 
                "id": "content-editor",
                "placeholder": "Write your post content here using Markdown or HTML...\n\n# Heading 1\n## Heading 2\n\n**Bold text** and *italic text*\n\n- Bullet point\n1. Numbered list\n\n```code block```\n\n![Image](url)\n[Link](url)"
            }),
            "committee": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "sports (optional)"}),
        }
        labels = {
            "thumbnail": "Thumbnail Image URL",
            "excerpt": "Preview Text",
            "content": "Post Content (Markdown/HTML)",
        }


class MediaFilterForm(forms.Form):
    MEDIA_TYPE_CHOICES = [
        ("", "All Media"),
        ("image", "Images"),
        ("video", "Videos"),
    ]
    media_type = forms.ChoiceField(
        choices=MEDIA_TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": INPUT_CLASS})
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Search media..."})
    )


class VideoForm(forms.ModelForm):
    class Meta:
        model = Video
        fields = ("title", "url", "image")
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "url": forms.URLInput(attrs={"class": INPUT_CLASS}),
            "image": forms.URLInput(attrs={"class": INPUT_CLASS}),
        }


class ChatMessageForm(forms.ModelForm):
    class Meta:
        model = ChatMessage
        fields = ("body",)
        widgets = {
            "body": forms.Textarea(attrs={"class": TEXTAREA_CLASS, "rows": 3}),
        }


class ChatTaskForm(forms.ModelForm):
    due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date", "class": INPUT_CLASS}))

    class Meta:
        model = ChatTask
        fields = ("title", "description", "priority", "status", "due_date", "assigned_to")
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "description": forms.Textarea(attrs={"class": TEXTAREA_CLASS}),
            "priority": forms.Select(attrs={"class": INPUT_CLASS}),
            "status": forms.Select(attrs={"class": INPUT_CLASS}),
            "assigned_to": forms.Select(attrs={"class": INPUT_CLASS}),
        }


class ChatTaskStatusForm(forms.ModelForm):
    class Meta:
        model = ChatTask
        fields = ("status",)
        widgets = {"status": forms.Select(attrs={"class": INPUT_CLASS})}


class ChatTaskAssignmentForm(forms.ModelForm):
    class Meta:
        model = ChatTask
        fields = ("assigned_to",)
        widgets = {"assigned_to": forms.Select(attrs={"class": INPUT_CLASS})}


class ChatTaskTodoForm(forms.ModelForm):
    class Meta:
        model = ChatTaskItem
        fields = ("label",)
        widgets = {"label": forms.TextInput(attrs={"class": INPUT_CLASS})}

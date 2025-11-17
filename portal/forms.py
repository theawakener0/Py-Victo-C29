from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import AccountUser, ChatMessage, ChatTask, ChatTaskItem, Post, Video


INPUT_CLASS = "w-full rounded-2xl border border-sage-200 dark:border-sage-700 bg-white/90 dark:bg-sage-900 text-sage-800 dark:text-cream-100 px-4 py-3"
TEXTAREA_CLASS = INPUT_CLASS + " h-36"


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
        fields = ("title", "content", "committee")
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "content": forms.Textarea(attrs={"class": TEXTAREA_CLASS}),
            "committee": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "sports"}),
        }


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

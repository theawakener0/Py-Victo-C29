from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("login.html", views.login_view),
    path("logout/", views.logout_view, name="logout"),
    path("register.html", views.signup_view, name="signup"),
    path("signup/", views.signup_view),
    
    # Posts (Blog-style)
    path("posts.html", views.posts_list, name="posts"),
    path("posts/", views.posts_list),
    path("posts/<slug:slug>", views.post_detail, name="post_detail"),
    path("create-posts.html", views.create_post, name="post_create"),
    path("create-posts/", views.create_post),
    path("admin/posts/<int:pk>/edit", views.edit_post, name="post_edit"),
    path("admin/posts/<int:pk>/delete", views.delete_post, name="post_delete"),
    
    # Post editor helpers (htmx)
    path("posts/editor/help", views.post_editor_help, name="post_editor_help"),
    path("posts/editor/preview", views.preview_post_content, name="post_preview"),
    
    # Media Gallery
    path("media/", views.media_list, name="media_list"),
    path("media.html", views.media_list),
    
    # Videos (legacy)
    path("videos.html", views.videos_list, name="videos"),
    path("create-videos.html", views.create_video, name="video_create"),
    path("create-videos/", views.create_video),
    path("admin/videos/<int:pk>/edit", views.edit_video, name="video_edit"),
    path("admin/videos/<int:pk>/delete", views.delete_video, name="video_delete"),
    
    path("legacy.html", views.legacy_view, name="legacy"),
    path("committees/<slug:key>.html", views.committee_view, name="committee"),
    path("admin/hub", views.admin_hub, name="admin_hub"),
    path("admin/hub/fragment/chat", views.admin_hub_chat_fragment, name="admin_hub_chat_fragment"),
    path("admin/hub/fragment/tasks", views.admin_hub_tasks_fragment, name="admin_hub_tasks_fragment"),
    path("admin/chat/events", views.admin_chat_stream, name="admin_chat_events"),
    path("admin/chat/messages/", views.create_chat_message, name="chat_message_create"),
    path("admin/chat/messages/<int:pk>/delete", views.delete_chat_message, name="chat_message_delete"),
    path("admin/chat/tasks/", views.create_chat_task, name="chat_task_create"),
    path("admin/chat/tasks/<int:pk>/status", views.update_task_status, name="chat_task_status"),
    path("admin/chat/tasks/<int:pk>/assignment", views.update_task_assignment, name="chat_task_assignment"),
    path("admin/chat/tasks/<int:pk>/todos", views.add_task_todo, name="chat_task_add_todo"),
    path("admin/chat/tasks/<int:pk>/delete", views.delete_task, name="chat_task_delete"),
    path("admin/chat/todos/<int:pk>/toggle", views.toggle_todo, name="chat_task_toggle_todo"),
]

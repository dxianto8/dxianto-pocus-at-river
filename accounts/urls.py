from django.contrib.auth import views as auth
from django.urls import path, reverse_lazy
from django.views.decorators.cache import never_cache

from . import views

app_name = "accounts"
urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path(
        "login/",
        auth.LoginView.as_view(
            template_name="accounts/login.html", redirect_authenticated_user=True
        ),
        name="login",
    ),
    path("logout/", auth.LogoutView.as_view(), name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("packages/", views.packages, name="packages"),
    path("settings/", views.settings, name="settings"),
    path("messages/", views.inbox, name="inbox"),
    path("bookings/<uuid:pk>/", views.booking_detail, name="booking_detail"),
    path("bookings/<uuid:pk>/edit/", views.booking_edit, name="booking_edit"),
    path("bookings/<uuid:pk>/cancel/", views.booking_cancel, name="booking_cancel"),
    path("bookings/<uuid:pk>/event.ics", views.booking_ics, name="booking_ics"),
    path("bookings/<uuid:pk>/messages/", views.booking_messages, name="booking_messages"),
    path("bookings/<uuid:pk>/checklist/", views.booking_checklist, name="booking_checklist"),
    path(
        "bookings/<uuid:pk>/checklist/<int:item_id>/",
        views.checklist_item,
        name="checklist_item",
    ),
    path("bookings/<uuid:pk>/schedule/", views.booking_schedule, name="booking_schedule"),
    path("bookings/<uuid:pk>/schedule/<int:item_id>/", views.schedule_item, name="schedule_item"),
    path("bookings/<uuid:pk>/documents/", views.booking_documents, name="booking_documents"),
    path("bookings/<uuid:pk>/documents/<uuid:document_id>/", views.document, name="document"),
    path(
        "password-reset/",
        auth.PasswordResetView.as_view(
            template_name="accounts/password_reset.html",
            email_template_name="accounts/password_reset_email.txt",
            subject_template_name="accounts/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/sent/",
        auth.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/complete/",
        auth.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    path(
        "password-change/",
        never_cache(
            auth.PasswordChangeView.as_view(
                template_name="accounts/password_change.html",
                success_url=reverse_lazy("accounts:password_change_done"),
            )
        ),
        name="password_change",
    ),
    path(
        "password-change/done/",
        never_cache(
            auth.PasswordChangeDoneView.as_view(template_name="accounts/password_change_done.html")
        ),
        name="password_change_done",
    ),
]

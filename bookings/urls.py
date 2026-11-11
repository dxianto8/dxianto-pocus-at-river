from django.urls import path

from . import views

app_name = "bookings"

urlpatterns = [
    path("", views.book, name="book"),
    path("requested/", views.requested, name="requested"),
]

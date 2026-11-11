from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

from bookings import views

admin.site.site_header = "Pocus at River admin"
admin.site.site_title = "Pocus at River admin"
admin.site.index_title = "Bookings and settings"

urlpatterns = [
    path("", views.home, name="home"),
    path("venue/", TemplateView.as_view(template_name="venue.html"), name="venue"),
    path("walk-throughs/", views.walkthrough, name="walkthrough"),
    path(
        "walk-throughs/requested/",
        TemplateView.as_view(template_name="walkthrough_requested.html"),
        name="walkthrough_requested",
    ),
    path("book/", include("bookings.urls")),
    path("admin/", admin.site.urls),
]

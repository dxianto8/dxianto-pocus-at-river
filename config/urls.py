from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

admin.site.site_header = "Pocus at River admin"
admin.site.site_title = "Pocus at River admin"
admin.site.index_title = "Bookings and settings"

urlpatterns = [
    path("", TemplateView.as_view(template_name="home.html"), name="home"),
    path("book/", include("bookings.urls")),
    path("admin/", admin.site.urls),
]

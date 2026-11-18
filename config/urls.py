from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

from bookings import catering_views, notifications, offering_views, site_views

admin.site.site_header = "Pocus at River admin"
admin.site.site_title = "Pocus at River admin"
admin.site.index_title = "Events, packages, and venue settings"

urlpatterns = [
    path("notifications/dispatch/", notifications.cron_dispatch, name="notification_dispatch"),
    path("notifications/sms/", notifications.sms_opt_out, name="sms_opt_out"),
    path("walkthroughs/", offering_views.walkthroughs, name="walkthroughs"),
    path("catering/", offering_views.catering, name="catering"),
    path("catering/order/", catering_views.catering_order, name="catering_order"),
    path(
        "catering/order/<uuid:pk>/",
        catering_views.catering_order_detail,
        name="catering_order_detail",
    ),
    path("recent-events/", offering_views.recent_events, name="recent_events"),
    path("", site_views.home, name="home"),
    path("explore/", site_views.home, name="explore"),
    path("weddings/", TemplateView.as_view(template_name="weddings.html"), name="weddings"),
    path("corporate/", TemplateView.as_view(template_name="corporate.html"), name="corporate"),
    path("gallery/", TemplateView.as_view(template_name="gallery.html"), name="gallery"),
    path("venue/", TemplateView.as_view(template_name="venue.html"), name="venue"),
    path("packages/", site_views.packages, name="packages"),
    path("account/", include("accounts.urls")),
    path("book/", include("bookings.urls")),
    path("admin/", admin.site.urls),
]

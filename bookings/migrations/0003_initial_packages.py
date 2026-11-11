from django.db import migrations


def seed(apps, schema_editor):
    Package = apps.get_model("bookings", "EventPackage")
    Settings = apps.get_model("bookings", "VenueSettings")
    Settings.objects.get_or_create(pk=1)
    for order, (slug, title, event_type, description) in enumerate([
        ("wedding", "Wedding celebrations", "wedding", "Start a conversation about your ceremony, reception, and the people you want beside you. We'll tailor the proposal to your plans."),
        ("corporate", "Company gatherings", "corporate", "Bring your team, clients, or collaborators together. Share your schedule, headcount, and meeting or celebration requirements."),
        ("celebration", "Private celebrations", "other", "Plan a birthday, anniversary, reunion, or a gathering that deserves its own space. Tell us what you're celebrating."),
    ]):
        Package.objects.get_or_create(slug=slug, defaults={
            "title": title, "event_type": event_type, "description": description,
            "is_published": True, "display_order": order,
        })


class Migration(migrations.Migration):
    dependencies = [("bookings", "0002_eventpackage_booking_owner_booking_package_snapshot_and_more")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]

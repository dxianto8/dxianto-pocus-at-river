from django.db import migrations


def seed(apps, schema_editor):
    EventType = apps.get_model("bookings", "EventTypeOption")
    for index, (code, label) in enumerate([
        ("wedding", "Wedding"), ("corporate", "Corporate event"), ("birthday", "Birthday"),
        ("anniversary", "Anniversary"), ("fundraiser", "Fundraiser or nonprofit event"),
        ("workshop", "Workshop or meeting"), ("reunion", "Reunion"), ("other", "Other"),
    ]):
        EventType.objects.get_or_create(code=code, defaults={"label": label, "display_order": index})


class Migration(migrations.Migration):
    dependencies = [("bookings", "0005_venue_services")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]

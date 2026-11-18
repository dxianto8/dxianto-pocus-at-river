from django import template
from django.utils.http import urlencode

register = template.Library()


@register.filter
def lookup(mapping, key):
    """`{{ mine|lookup:day }}` for dictionaries keyed by something other than a string."""
    return mapping.get(key) if mapping else None


@register.filter
def filesize(size):
    if size < 1024 * 1024:
        return f"{max(size // 1024, 1)} KB"
    return f"{size / 1024 / 1024:.1f} MB"


@register.simple_tag
def pick_url(package, month, day, session):
    """Link that picks a date and time of day on the booking calendar."""
    params = {"package": package} if package else {}
    params.update(month=f"{month:%Y-%m}", date=day.isoformat(), session=session)
    return f"?{urlencode(params)}#request"

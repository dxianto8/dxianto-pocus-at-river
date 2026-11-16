from django import template

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

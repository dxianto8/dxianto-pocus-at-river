"""
Reading an uploaded catering menu (PDF or photo) into menu items with Claude.

One request per upload: the file goes in as a document or image block, and structured output
(`output_config.format`) makes the answer JSON in a fixed shape. Nothing is published here;
items are saved as drafts for staff to check (`apply_reading`), because a misread price is
worse than no price. Needs ANTHROPIC_API_KEY in the environment.
"""

import base64
import json
import logging
import os
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

import anthropic
from django.db import transaction
from django.utils import timezone

from .models import CateringItem, MenuUpload

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"
# Transcription needs care, not long reasoning; low effort keeps an admin upload well inside
# a serverless function's time limit.
EFFORT = "low"
# One attempt plus one SDK retry (429s, 5xx, timeouts) stays under Vercel's 300-second cap.
TIMEOUT_SECONDS = 140
MAX_RETRIES = 1

SYSTEM = """You transcribe catering menus for an event venue's website. Guests will order from \
what you write, so accuracy matters more than completeness.

- Copy item names, descriptions and prices exactly as printed. Do not invent, improve or \
translate anything. Fix only obvious line-break hyphenation.
- Use the menu's own section headings as categories, in the order they appear. If the menu \
has no headings, use a single category called "Menu".
- Prices are in US dollars. Write the amount as digits with two decimals, like "12.50", with \
no currency sign. If no price is printed for an item, use an empty string.
- Put how the price applies (for example "per person", "per dozen", "serves 10") in \
price_note, exactly as printed. If an item has several sizes or prices, make one item per \
size and name the size in price_note.
- Put dietary marks in dietary_notes as words ("Vegetarian", "Gluten-free"), using the \
menu's key if it has one.
- List in warnings anything you could not read clearly or had to guess, naming the item."""

INSTRUCTION = "Transcribe this catering menu."

ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "description": "The section heading, as printed."},
        "title": {"type": "string"},
        "description": {"type": "string", "description": "Empty string if none."},
        "dietary_notes": {"type": "string", "description": "Empty string if none."},
        "price": {
            "type": "string",
            "description": 'Digits with two decimals, like "12.50"; empty string if none.',
        },
        "price_note": {"type": "string", "description": "Empty string if none."},
    },
    "required": ["category", "title", "description", "dietary_notes", "price", "price_note"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": ITEM_SCHEMA},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["items", "warnings"],
    "additionalProperties": False,
}


class MenuReadError(Exception):
    """A reading failed; the message is written for staff and is safe to show them."""


@dataclass
class ReadItem:
    category: str
    title: str
    description: str = ""
    dietary_notes: str = ""
    price: Decimal | None = None
    price_note: str = ""


@dataclass
class Reading:
    items: list[ReadItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _file_block(data: bytes, content_type: str) -> dict:
    encoded = base64.standard_b64encode(data).decode("ascii")
    kind = "document" if content_type == "application/pdf" else "image"
    return {"type": kind, "source": {"type": "base64", "media_type": content_type, "data": encoded}}


def _request(data: bytes, content_type: str):
    """The API call itself, kept apart so tests can replace it."""
    client = anthropic.Anthropic(timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)
    return client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        # If a safety classifier declines, the API retries on its recommended fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={
            "effort": EFFORT,
            "format": {"type": "json_schema", "schema": SCHEMA},
        },
        system=SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [_file_block(data, content_type), {"type": "text", "text": INSTRUCTION}],
            }
        ],
    )


def _price(value: str, title: str, warnings: list[str]) -> Decimal | None:
    value = (value or "").strip().lstrip("$").replace(",", "")
    if not value:
        return None
    try:
        price = Decimal(value).quantize(Decimal("0.01"))
    except InvalidOperation:
        warnings.append(f"{title}: the price “{value}” was not a number, so it was left blank.")
        return None
    if price < 0 or price >= Decimal("1000000"):
        warnings.append(f"{title}: the price {value} looks wrong, so it was left blank.")
        return None
    return price


def read_menu(data: bytes, content_type: str) -> Reading:
    """Ask Claude to transcribe a menu file. Raises MenuReadError with a staff-facing reason."""
    if not is_configured():
        raise MenuReadError(
            "AI reading is not set up: add ANTHROPIC_API_KEY to the site's environment "
            "variables. You can still add the items by hand below."
        )
    try:
        response = _request(data, content_type)
    except anthropic.BadRequestError as error:
        logger.warning("Menu reading rejected: %s", error.message)
        raise MenuReadError(
            "The file could not be read. Try a clearer photo or a PDF of the menu."
        ) from error
    except anthropic.AuthenticationError as error:
        raise MenuReadError("The ANTHROPIC_API_KEY was not accepted. Check the key.") from error
    except anthropic.PermissionDeniedError as error:
        raise MenuReadError("The API key is not allowed to use this model.") from error
    except anthropic.RateLimitError as error:
        raise MenuReadError(
            "Too many requests just now. Wait a minute and read it again."
        ) from error
    except anthropic.APITimeoutError as error:
        raise MenuReadError("Reading took too long. Try again, or split a long menu.") from error
    except anthropic.APIStatusError as error:
        logger.warning("Menu reading failed with status %s", error.status_code)
        raise MenuReadError("The reading service had a problem. Try again shortly.") from error
    except anthropic.APIConnectionError as error:
        raise MenuReadError("The reading service could not be reached. Try again.") from error

    if response.stop_reason == "refusal":
        raise MenuReadError("The file was declined by the reading service. Check it is the menu.")
    if response.stop_reason == "max_tokens":
        raise MenuReadError("The menu is too long to read at once. Upload it in parts.")
    text = next((block.text for block in response.content if block.type == "text"), "")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise MenuReadError("The reading came back incomplete. Read it again.") from error

    warnings = [str(w).strip() for w in payload.get("warnings", []) if str(w).strip()]
    items = []
    for raw in payload.get("items", []):
        title = (raw.get("title") or "").strip()[:120]
        if not title:
            continue
        items.append(
            ReadItem(
                category=(raw.get("category") or "").strip()[:80] or "Menu",
                title=title,
                description=(raw.get("description") or "").strip()[:1000],
                dietary_notes=(raw.get("dietary_notes") or "").strip()[:200],
                price=_price(raw.get("price", ""), title, warnings),
                price_note=(raw.get("price_note") or "").strip()[:120],
            )
        )
    if not items:
        raise MenuReadError("No menu items were found in that file.")
    return Reading(items=items, warnings=warnings)


def read_upload(upload: MenuUpload) -> int:
    """Read an upload into draft items, replacing earlier unpublished drafts from it."""
    try:
        reading = read_menu(bytes(upload.data), upload.content_type)
    except MenuReadError as error:
        upload.status = MenuUpload.Status.FAILED
        upload.error = str(error)[:300]
        upload.save(update_fields=["status", "error"])
        raise
    categories = list(dict.fromkeys(item.category for item in reading.items))
    with transaction.atomic():
        upload.items.filter(is_published=False).delete()
        CateringItem.objects.bulk_create(
            CateringItem(
                source_upload=upload,
                category=item.category,
                category_order=categories.index(item.category) + 1,
                display_order=position,
                title=item.title,
                description=item.description,
                dietary_notes=item.dietary_notes,
                price=item.price,
                price_note=item.price_note,
                is_published=False,
            )
            for position, item in enumerate(reading.items, start=1)
        )
        upload.status = MenuUpload.Status.READ
        upload.error = ""
        upload.notes = "\n".join(reading.warnings)
        upload.read_at = timezone.now()
        upload.save(update_fields=["status", "error", "notes", "read_at"])
    return len(reading.items)


def publish_upload(upload: MenuUpload) -> int:
    """Make this upload's items the catering menu. Items from elsewhere are taken off the menu."""
    with transaction.atomic():
        CateringItem.objects.filter(is_published=True).exclude(source_upload=upload).update(
            is_published=False
        )
        count = upload.items.update(is_published=True)
        MenuUpload.objects.filter(status=MenuUpload.Status.PUBLISHED).exclude(pk=upload.pk).update(
            status=MenuUpload.Status.READ, published_at=None
        )
        upload.status = MenuUpload.Status.PUBLISHED
        upload.published_at = timezone.now()
        upload.save(update_fields=["status", "published_at"])
    return count

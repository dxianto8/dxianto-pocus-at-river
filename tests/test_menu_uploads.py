"""Uploading a catering menu in the admin and having Claude read it into draft items."""

import json
from decimal import Decimal
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from bookings import menu_reader
from bookings.models import CateringItem, MenuUpload

pytestmark = pytest.mark.django_db

MENU = {
    "items": [
        {
            "category": "Starters",
            "title": "Grazing board",
            "description": "Cheese, fruit and bread",
            "dietary_notes": "Vegetarian",
            "price": "12.50",
            "price_note": "per person",
        },
        {
            "category": "Starters",
            "title": "Soup shooters",
            "description": "",
            "dietary_notes": "",
            "price": "market",
            "price_note": "",
        },
        {
            "category": "Desserts",
            "title": "Celebration cake",
            "description": "Three tiers",
            "dietary_notes": "",
            "price": "",
            "price_note": "",
        },
    ],
    "warnings": ["Signature cake: the price was smudged."],
}


def reply(payload=MENU, stop_reason="end_turn"):
    text = json.dumps(payload) if isinstance(payload, dict) else payload
    return SimpleNamespace(
        stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)]
    )


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


@pytest.fixture
def claude(monkeypatch, api_key):
    """Replace the API call; tests set .result (a reply or an exception) and read .calls."""
    state = SimpleNamespace(result=reply(), calls=[])

    def fake(data, content_type):
        state.calls.append((data, content_type))
        if isinstance(state.result, Exception):
            raise state.result
        return state.result

    monkeypatch.setattr(menu_reader, "_request", fake)
    return state


def pdf(name="menu.pdf", content=b"%PDF-1.4 menu"):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


def make_upload(**fields):
    upload = MenuUpload(title="Spring menu", **fields)
    upload.attach(pdf())
    upload.save()
    return upload


class TestReading:
    def test_items_prices_and_warnings(self, claude):
        reading = menu_reader.read_menu(b"%PDF", "application/pdf")
        board, soup, cake = reading.items
        assert (board.category, board.title, board.price, board.price_note) == (
            "Starters",
            "Grazing board",
            Decimal("12.50"),
            "per person",
        )
        assert soup.price is None and cake.price is None
        assert "Signature cake: the price was smudged." in reading.warnings
        assert any("Soup shooters" in w and "not a number" in w for w in reading.warnings)

    def test_not_configured_says_how_to_fix_it(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(menu_reader.MenuReadError, match="ANTHROPIC_API_KEY"):
            menu_reader.read_menu(b"%PDF", "application/pdf")

    @pytest.mark.parametrize(
        ("result", "message"),
        [
            (reply(stop_reason="refusal"), "declined"),
            (reply(stop_reason="max_tokens"), "too long"),
            (reply("{not json"), "incomplete"),
            (reply({"items": [], "warnings": []}), "No menu items"),
            (
                anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x")),
                "could not be reached",
            ),
            (anthropic.APITimeoutError(request=httpx2.Request("POST", "https://x")), "too long"),
        ],
    )
    def test_failures_become_plain_messages(self, claude, result, message):
        claude.result = result
        with pytest.raises(menu_reader.MenuReadError, match=message):
            menu_reader.read_menu(b"%PDF", "application/pdf")

    def test_request_shape(self, monkeypatch, api_key):
        sent = {}

        class FakeMessages:
            def create(self, **kwargs):
                sent.update(kwargs)
                return reply()

        class FakeClient:
            def __init__(self, **options):
                sent["client"] = options
                self.beta = SimpleNamespace(messages=FakeMessages())

        monkeypatch.setattr(menu_reader.anthropic, "Anthropic", FakeClient)
        menu_reader.read_menu(b"%PDF-1.4", "application/pdf")
        assert sent["model"] == "claude-opus-5-5"
        assert sent["fallbacks"] == "default"
        assert sent["betas"] == ["server-side-fallback-2026-07-01"]
        assert sent["output_config"]["format"]["type"] == "json_schema"
        assert sent["output_config"]["format"]["schema"] == menu_reader.SCHEMA
        block = sent["messages"][0]["content"][0]
        assert block["type"] == "document"
        assert block["source"]["media_type"] == "application/pdf"
        assert sent["client"]["timeout"] * (sent["client"]["max_retries"] + 1) < 300

        menu_reader.read_menu(b"\xff\xd8", "image/jpeg")
        assert sent["messages"][0]["content"][0]["type"] == "image"


class TestDraftsAndPublishing:
    def test_reading_makes_unpublished_drafts_in_menu_order(self, claude):
        upload = make_upload()
        assert menu_reader.read_upload(upload) == 3
        upload.refresh_from_db()
        assert upload.status == MenuUpload.Status.READ
        assert "smudged" in upload.notes
        items = list(upload.items.all())
        assert not any(item.is_published for item in items)
        # The menu's own section order wins over the alphabet: Starters before Desserts.
        assert [i.title for i in items] == ["Grazing board", "Soup shooters", "Celebration cake"]

    def test_reading_again_replaces_drafts(self, claude):
        upload = make_upload()
        menu_reader.read_upload(upload)
        menu_reader.read_upload(upload)
        assert upload.items.count() == 3

    def test_failure_is_recorded(self, claude):
        claude.result = reply(stop_reason="refusal")
        upload = make_upload()
        with pytest.raises(menu_reader.MenuReadError):
            menu_reader.read_upload(upload)
        upload.refresh_from_db()
        assert upload.status == MenuUpload.Status.FAILED and "declined" in upload.error

    def test_publishing_replaces_the_live_menu(self, claude, client):
        old = CateringItem.objects.create(
            title="Old dish", category="Mains", description="x", is_published=True
        )
        upload = make_upload()
        menu_reader.read_upload(upload)
        html = client.get(reverse("catering")).content.decode()
        assert "Old dish" in html and "Grazing board" not in html
        assert menu_reader.publish_upload(upload) == 3
        old.refresh_from_db()
        assert not old.is_published
        html = client.get(reverse("catering")).content.decode()
        assert "Grazing board" in html and "Old dish" not in html
        assert html.index("Starters") < html.index("Desserts")


class TestAdmin:
    def test_upload_reads_and_opens_the_review_screen(self, claude, admin_client):
        response = admin_client.post(
            reverse("admin:bookings_menuupload_add"), {"title": "Spring", "upload": pdf()}
        )
        upload = MenuUpload.objects.get()
        assert response.url == reverse("admin:bookings_menuupload_change", args=[upload.pk])
        assert upload.items.count() == 3 and upload.uploaded_by.is_superuser
        page = admin_client.get(response.url)
        html = page.content.decode()
        assert "Publish to the catering menu" in html and "Grazing board" in html
        assert admin_client.get(
            reverse("admin:bookings_menuupload_file", args=[upload.pk])
        ).content.startswith(b"%PDF")

    @pytest.mark.parametrize(
        ("name", "content", "error"),
        [
            ("menu.heic", b"x", "JPG"),
            ("menu.docx", b"x", "PDF, JPG"),
            ("menu.pdf", b"x" * (4 * 1024 * 1024 + 1), "larger than 4 MB"),
        ],
    )
    def test_unsuitable_files_are_refused(self, claude, admin_client, name, content, error):
        response = admin_client.post(
            reverse("admin:bookings_menuupload_add"),
            {"title": "Spring", "upload": SimpleUploadedFile(name, content)},
        )
        assert response.status_code == 200
        assert error in response.content.decode()
        assert not MenuUpload.objects.exists() and not claude.calls

    def test_upload_without_a_key_still_works_and_says_why(self, monkeypatch, admin_client):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        response = admin_client.post(
            reverse("admin:bookings_menuupload_add"),
            {"title": "Spring", "upload": pdf()},
            follow=True,
        )
        assert "ANTHROPIC_API_KEY" in response.content.decode()
        assert MenuUpload.objects.get().status == MenuUpload.Status.FAILED

    def test_publish_and_read_again_buttons(self, claude, admin_client):
        upload = make_upload()
        menu_reader.read_upload(upload)
        url = reverse("admin:bookings_menuupload_change", args=[upload.pk])
        data = change_form_data(admin_client, url)
        admin_client.post(url, {**data, "_read_again": "1"})
        assert len(claude.calls) == 2
        admin_client.post(url, {**change_form_data(admin_client, url), "_publish": "1"})
        upload.refresh_from_db()
        assert upload.status == MenuUpload.Status.PUBLISHED
        assert upload.items.filter(is_published=True).count() == 3
        # A live menu is not read again; a new file goes in as a new upload.
        html = admin_client.get(url).content.decode()
        assert "Read again with AI" not in html


def change_form_data(client, url):
    """The change form's current values, as the browser would post them back."""
    response = client.get(url)
    data = {"title": response.context["original"].title}
    for inline in response.context["inline_admin_formsets"]:
        formset = inline.formset
        management = formset.management_form
        for name in management.fields:
            data[f"{formset.prefix}-{name}"] = management[name].value()
        for form in formset.forms:
            for name in form.fields:
                value = form[name].value()
                if value is not None and value is not False:
                    data[form.add_prefix(name)] = value
    return data

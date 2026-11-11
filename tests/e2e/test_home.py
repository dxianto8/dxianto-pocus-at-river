import re

import pytest
from playwright.sync_api import Page, expect


def test_home_has_full_width_photography_and_new_navigation(page: Page):
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto("/")
    expect(page.get_by_role("heading", level=1)).to_have_text(
        "A place with a story. An event that's yours."
    )
    hero = page.get_by_test_id("hero").bounding_box()
    assert hero["x"] == 0 and hero["width"] == 1440
    nav = page.get_by_role("navigation")
    for label, path in [
        ("Weddings", "/weddings/"),
        ("Corporate", "/corporate/"),
        ("Gallery", "/gallery/"),
        ("Packages & pricing", "/packages/"),
    ]:
        expect(nav.get_by_role("link", name=label, exact=True)).to_have_attribute("href", path)
    assert (
        page.get_by_role("heading", level=1).evaluate("el=>getComputedStyle(el).fontStyle")
        == "normal"
    )


@pytest.mark.parametrize("width", [360, 390, 768, 1440])
@pytest.mark.parametrize(
    "url",
    [
        "/",
        "/weddings/",
        "/corporate/",
        "/venue/",
        "/gallery/",
        "/packages/",
        "/account/login/",
        "/account/signup/",
    ],
)
def test_public_pages_fit_the_viewport(page: Page, width, url):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(url)
    assert page.evaluate(
        "document.documentElement.scrollWidth<=document.documentElement.clientWidth"
    )
    expect(page.get_by_role("heading", level=1)).to_be_visible()


def test_gallery_keyboard_controls(page: Page):
    page.goto("/gallery/")
    photos = page.locator("[data-gallery]")
    photos.first.click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    page.keyboard.press("ArrowRight")
    expect(dialog.locator("img")).to_have_attribute("src", re.compile("wedding-couple.jpg$"))
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    expect(photos.first).to_be_focused()


def test_mobile_menu_and_account_gate(page: Page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/")
    page.get_by_role("button", name="Menu").click()
    page.get_by_role("navigation").get_by_role("link", name="Plan an event").click()
    expect(page).to_have_url(re.compile(r"/account/login/\?next="))
    expect(page.get_by_role("heading", name="Log in to your account")).to_be_visible()


def test_signup_to_booking_to_status_dashboard(page: Page):
    from datetime import timedelta

    from django.utils import timezone

    from bookings.models import Booking

    day = timezone.localdate() + timedelta(days=12)
    page.goto(f"/book/?date={day:%Y-%m-%d}")
    page.get_by_role("link", name="Create an account", exact=True).click()
    page.get_by_label("Your name", exact=True).fill("New Guest")
    page.get_by_label("Email", exact=True).fill("new@example.com")
    page.get_by_label("Username", exact=True).fill("newguest")
    page.get_by_label("Password", exact=True).fill("Strong-River-Password-2027!")
    page.get_by_label("Password confirmation", exact=True).fill("Strong-River-Password-2027!")
    page.get_by_role("button", name="Create account").click()
    expect(page.get_by_label("Email", exact=True)).to_be_disabled()
    page.get_by_label("Event type").select_option("wedding")
    page.get_by_label("Number of guests").fill("60")
    page.get_by_role("button", name="Send Request").click()
    expect(page.get_by_role("heading", name="Thank You")).to_be_visible()
    page.get_by_role("link", name="View my request").click()
    expect(page.locator(".status")).to_have_text("Pending")
    booking = Booking.objects.get()
    assert booking.owner.username == "newguest"
    booking.status = Booking.Status.CONFIRMED
    booking.save()
    page.reload()
    expect(page.locator(".status")).to_have_text("Confirmed")


def test_core_flows_without_javascript(browser, base_url):
    context = browser.new_context(java_script_enabled=False, base_url=base_url)
    page = context.new_page()
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/")
    expect(page.get_by_role("navigation")).to_be_visible()
    page.get_by_role("navigation").get_by_role("link", name="Packages & pricing").click()
    page.get_by_text("Does submitting a request confirm my event?", exact=True).click()
    expect(page.locator("details[open]")).to_contain_text("No.")
    context.close()

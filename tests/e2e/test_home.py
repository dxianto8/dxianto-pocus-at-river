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
    assert hero["x"] == 0 and hero["width"] == page.locator("body").bounding_box()["width"]
    nav = page.get_by_role("navigation")
    for group, label, path in [
        ("Events", "Weddings", "/weddings/"),
        ("Events", "Corporate", "/corporate/"),
        ("The venue", "Gallery", "/gallery/"),
        ("Pricing", "Packages & pricing", "/packages/"),
    ]:
        nav.get_by_role("button", name=group).hover()
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


def test_mobile_menu_plan_event_opens_the_calendar_without_an_account(page: Page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/")
    page.get_by_role("button", name="Menu").click()
    page.get_by_role("navigation").get_by_role("link", name="Plan an event").click()
    expect(page).to_have_url(re.compile(r"/book/$"))
    expect(page.get_by_role("heading", level=1, name="Request a date")).to_be_visible()
    expect(page.get_by_test_id("calendar")).to_be_visible()
    expect(page.get_by_text("No account needed.")).to_be_visible()


def test_signup_to_booking_to_status_dashboard(page: Page):
    from datetime import timedelta

    from django.utils import timezone

    from bookings.models import Booking

    day = timezone.localdate() + timedelta(days=12)
    page.goto("/")
    page.locator(".header-account").get_by_role("link", name="Sign up").click()
    expect(page).to_have_url(re.compile(r"/account/signup/\?next="))
    page.get_by_label("Your name", exact=True).fill("New Guest")
    page.get_by_label("Email", exact=True).fill("new@example.com")
    page.get_by_label("Username", exact=True).fill("newguest")
    page.get_by_label("Password", exact=True).fill("Strong-River-Password-2027!")
    page.get_by_label("Password confirmation", exact=True).fill("Strong-River-Password-2027!")
    page.get_by_role("button", name="Create account").click()
    expect(page).to_have_url(re.compile(r"/book/$"))
    expect(page.get_by_test_id("calendar")).to_be_visible()
    expect(page.get_by_role("navigation", name="Workspace navigation")).to_be_visible()
    page.goto(f"/book/?date={day:%Y-%m-%d}")
    expect(page.get_by_label("Email", exact=True)).to_be_disabled()
    page.get_by_label("Phone", exact=True).fill("630 555 0100")
    page.get_by_label("Event type").select_option("wedding")
    page.get_by_label("Number of guests").fill("60")
    page.get_by_role("button", name="Send Request").click()
    expect(page.get_by_role("heading", name="Request received")).to_be_visible()
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


@pytest.mark.parametrize("width", [390, 1440])
def test_workspace_navigation_and_account_pages(page: Page, customer_login, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto("/account/")
    expect(page.get_by_role("heading", level=1)).to_contain_text("Hello")
    for path in ["/account/", "/book/", "/account/packages/", "/account/settings/"]:
        page.goto(path)
        assert page.evaluate(
            "document.documentElement.scrollWidth<=document.documentElement.clientWidth"
        )
        expect(page.get_by_role("main")).to_be_visible()
        expect(page.locator(".site-footer")).to_have_count(0)
    if width < 1024:
        button = page.get_by_role("button", name="Open workspace navigation")
        button.click()
        expect(page.get_by_role("navigation", name="Workspace navigation")).to_be_visible()
        page.keyboard.press("Escape")
        expect(button).to_be_focused()
        expect(page.get_by_role("navigation", name="Workspace navigation")).not_to_be_visible()


def test_existing_account_can_continue_plan_event_through_login(page: Page):
    from django.contrib.auth import get_user_model

    get_user_model().objects.create_user(
        "returning", "returning@example.com", "Strong-River-Password-2027!"
    )
    page.goto("/book/?package=wedding")
    page.locator(".booking__account").get_by_role("link", name="Sign in").click()
    page.get_by_label("Username", exact=True).fill("returning")
    page.get_by_label("Password", exact=True).fill("Strong-River-Password-2027!")
    page.get_by_role("button", name="Sign in", exact=True).click()
    expect(page).to_have_url(re.compile(r"/book/\?package=wedding$"))
    expect(page.get_by_test_id("calendar")).to_be_visible()


def test_navigation_groups_open_on_hover_and_keyboard(page: Page):
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto("/weddings/")
    toggle = page.get_by_role("button", name="The venue")
    menu = page.locator("#nav-venue")
    expect(menu).to_be_hidden()
    toggle.hover()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(menu).to_be_visible()
    # Moving down into the panel keeps it open; clicking right after hovering does too.
    menu.get_by_role("link", name="Gallery").hover()
    expect(menu).to_be_visible()
    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    page.mouse.move(700, 700)
    expect(menu).to_be_hidden()
    # Keyboard: ArrowDown opens and moves in, Escape closes and returns focus.
    toggle.focus()
    page.keyboard.press("ArrowDown")
    expect(menu.get_by_role("link", name="About & directions")).to_be_focused()
    page.keyboard.press("Escape")
    expect(menu).to_be_hidden()
    expect(toggle).to_be_focused()


HIDDEN = """() => [...document.querySelectorAll('main *')].filter(el => {
  const style = getComputedStyle(el);
  const box = el.getBoundingClientRect();
  return box.width > 0 && el.tagName !== 'FIGCAPTION' && (
    style.opacity === '0' ||
    /inset\\((?!0px\\))/.test(style.clipPath) && !el.matches('.page-head'));
}).map(el => el.className || el.tagName)"""


@pytest.mark.parametrize("url", ["/", "/weddings/", "/gallery/", "/packages/"])
def test_entrances_leave_nothing_hidden(page: Page, url):
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(url)
    page.evaluate(
        """async () => {
          for (let y = 0; y < document.body.scrollHeight; y += 300) {
            window.scrollTo(0, y); await new Promise(r => setTimeout(r, 100));
          }
        }"""
    )
    # Photos wait to load before they are uncovered, so allow for a slow test server.
    page.wait_for_function("document.querySelectorAll('[data-reveal]').length === 0", timeout=10000)
    page.wait_for_timeout(300)
    assert page.evaluate(HIDDEN) == []


def test_reduced_motion_never_holds_anything_back(browser, base_url):
    context = browser.new_context(reduced_motion="reduce", base_url=base_url)
    page = context.new_page()
    page.goto("/")
    assert "motion" not in page.evaluate("document.documentElement.className")
    assert page.evaluate(HIDDEN) == []
    context.close()

import re

import pytest
from playwright.sync_api import Page, expect

from bookings.models import Testimonial as GuestTestimonial
from bookings.models import WalkthroughRequest


def test_home_links_to_the_event_calendar_and_venue(page: Page):
    page.goto("/")
    expect(page.get_by_role("heading", level=1)).to_have_accessible_name(
        "Pocus at River, weddings & events"
    )
    expect(
        page.get_by_test_id("hero").get_by_role("link", name="Book Your Date")
    ).to_have_attribute("href", "/book/")
    page.get_by_role("link", name="Get to know the venue").click()
    expect(page).to_have_url(re.compile(r"/venue/$"))
    expect(page.get_by_role("link", name="Get Directions")).to_have_attribute(
        "href", re.compile(r"google.com/maps/dir/.*Aurora")
    )


@pytest.mark.parametrize("width", [360, 390, 768, 1440])
@pytest.mark.parametrize("url", ["/", "/venue/", "/walk-throughs/", "/book/"])
def test_public_pages_fit_the_viewport(page: Page, width, url):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(url)
    assert page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )
    expect(page.get_by_role("heading", level=1)).to_be_visible()


def test_phone_navigation_can_open_close_and_navigate(page: Page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/")
    nav = page.get_by_role("navigation", name="Main navigation")
    expect(nav).not_to_be_visible()
    menu = page.get_by_role("button", name="Menu")
    menu.click()
    expect(nav).to_be_visible()
    page.keyboard.press("Escape")
    expect(nav).not_to_be_visible()
    expect(menu).to_be_focused()
    menu.click()
    nav.get_by_role("link", name="Walk-throughs").click()
    expect(page).to_have_url(re.compile(r"/walk-throughs/$"))
    expect(page.get_by_role("checkbox")).not_to_be_checked()


def test_gallery_supports_keyboard_navigation_and_restores_focus(page: Page):
    page.goto("/")
    photos = page.get_by_test_id("gallery").get_by_role("link")
    expect(photos).to_have_count(3)
    photos.nth(0).click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    expect(dialog.locator("img")).to_have_attribute("src", re.compile(r"hero.jpg$"))
    page.keyboard.press("ArrowRight")
    expect(dialog.locator("img")).to_have_attribute("src", re.compile(r"gallery-dance.jpg$"))
    dialog.get_by_role("button", name="Previous photo").click()
    expect(dialog.locator("img")).to_have_attribute("src", re.compile(r"hero.jpg$"))
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    expect(photos.nth(0)).to_be_focused()


def test_faq_expands_and_has_booking_links(page: Page):
    page.goto("/")
    question = page.get_by_text("Can I see the venue before booking?", exact=True)
    question.click()
    expect(page.locator("details[open]")).to_contain_text("subject to confirmation")
    expect(page.locator("details[open]").get_by_role("link")).to_have_attribute(
        "href", "/walk-throughs/"
    )


def test_walkthrough_submission_reaches_real_confirmation(page: Page):
    from datetime import timedelta

    from django.utils import timezone

    page.goto("/walk-throughs/")
    page.get_by_label("Your name").fill("Tour Guest")
    page.get_by_label("Email *", exact=True).fill("tour@example.com")
    page.get_by_label("Preferred visit date").fill(
        (timezone.localdate() + timedelta(days=10)).isoformat()
    )
    page.get_by_label("Preferred time of day").select_option("afternoon")
    page.get_by_role("checkbox").check()
    page.get_by_role("button", name="Request a Walk-through").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Your walk-through request is in.")
    assert WalkthroughRequest.objects.get().email == "tour@example.com"


def test_real_testimonials_can_be_browsed_without_autoplay(page: Page):
    for order, quote in enumerate(["First approved guest story.", "Second approved guest story."]):
        GuestTestimonial.objects.create(
            quote=quote,
            attribution=f"Guest {order}",
            permission_granted=True,
            is_published=True,
            display_order=order,
        )
    page.goto("/")
    expect(page.get_by_text("“First approved guest story.”")).to_be_visible()
    expect(page.get_by_text("“Second approved guest story.”")).not_to_be_visible()
    page.get_by_role("button", name="Next testimonial").click()
    expect(page.get_by_text("“Second approved guest story.”")).to_be_visible()
    page.get_by_role("button", name="Previous testimonial").click()
    expect(page.get_by_text("“First approved guest story.”")).to_be_visible()


def test_navigation_and_faq_work_without_javascript(browser, base_url):
    context = browser.new_context(java_script_enabled=False, base_url=base_url)
    page = context.new_page()
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/")
    expect(page.get_by_role("navigation")).to_be_visible()
    page.get_by_text("Can I see the venue before booking?", exact=True).click()
    expect(page.locator("details[open]")).to_contain_text("subject to confirmation")
    page.get_by_role("navigation").get_by_role("link", name="Walk-throughs").click()
    expect(page.get_by_label("Preferred visit date")).to_be_visible()
    context.close()


def test_parallax_respects_reduced_motion(page: Page):
    page.emulate_media(reduced_motion="reduce")
    page.goto("/")
    page.evaluate("window.scrollTo(0, 200)")
    assert page.get_by_test_id("hero-photo").evaluate("el => el.style.transform") == ""

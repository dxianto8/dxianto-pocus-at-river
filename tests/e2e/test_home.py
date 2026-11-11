import re

import pytest
from playwright.sync_api import Locator, Page, expect


def box(locator: Locator) -> dict:
    b = locator.bounding_box()
    assert b, "element has no bounding box"
    return b


def page_box(page: Page, locator: Locator) -> dict:
    """Position on the page (not the viewport), comparable with the original's measurements."""
    b = box(locator)
    return {**b, "y": b["y"] + page.evaluate("window.scrollY")}


def gallery(page: Page) -> Locator:
    return page.get_by_test_id("gallery").get_by_role("img")


def near(actual: float, expected: float, tolerance: float = 4) -> None:
    assert abs(actual - expected) <= tolerance, f"{actual} not within {tolerance}px of {expected}"


@pytest.fixture
def desktop(page: Page) -> Page:
    page.set_viewport_size({"width": 1440, "height": 900})
    return page


class TestContent:
    def test_title_and_accessible_h1(self, page: Page):
        page.goto("/")
        expect(page).to_have_title("HOME | Pocus At River")
        expect(
            page.get_by_role("heading", level=1, name="Pocus at River, weddings & events")
        ).to_be_visible()

    def test_section_headings_in_order(self, page: Page):
        page.goto("/")
        expect(page.get_by_role("heading", level=2)).to_have_text(
            [
                "Host Your Event at the Historic Pocus Motors Building",
                "Tell Us About Your Event",
                "Get in Touch",
            ]
        )

    def test_original_text_word_for_word(self, page: Page):
        page.goto("/")
        expect(
            page.get_by_text(re.compile(r"^Say \"I do\" in one of downtown Aurora's"))
        ).to_be_visible()
        expect(
            page.get_by_text(re.compile(r"so it's worth locking in your date now\.$"))
        ).to_be_visible()
        expect(page.get_by_text("100 S. River Street, Downtown Aurora IL")).to_be_visible()
        expect(page.get_by_text("© 2026 by Pocus at River")).to_be_visible()

    def test_enquire_goes_to_booking_page_and_email_us_opens_email(self, page: Page):
        page.goto("/")
        expect(page.get_by_role("link", name="Enquire About Your Event")).to_have_attribute(
            "href", "/book/"
        )
        expect(page.get_by_role("link", name="Email Us")).to_have_attribute(
            "href", "mailto:events@pocusatriver.com?subject=Event%20Inquiry"
        )

    def test_social_links(self, page: Page):
        page.goto("/")
        expect(page.get_by_role("link", name="Instagram")).to_have_attribute(
            "href", "https://www.instagram.com/pocusatriver"
        )
        expect(page.get_by_role("link", name="Facebook")).to_have_attribute(
            "href", "https://www.facebook.com/pocusatriver"
        )

    def test_gallery_has_three_photos_with_alt_text(self, page: Page):
        page.goto("/")
        expect(gallery(page)).to_have_count(3)
        for photo in gallery(page).all():
            expect(photo).to_have_attribute("alt", re.compile(r"\S"))


class TestMatchesOriginalAt1440:
    """Measurements taken from the original site at 1440x900 on 2026-11-11."""

    def test_hero_badge_and_address(self, desktop: Page):
        desktop.goto("/")
        hero = page_box(desktop, desktop.get_by_test_id("hero"))
        assert (hero["x"], hero["y"], hero["width"], hero["height"]) == (80, 79, 1280, 821)

        badge = page_box(desktop, desktop.get_by_role("heading", level=1).get_by_role("img"))
        near(badge["x"], 597, 1)
        near(badge["y"], 235, 1)
        near(badge["width"], 245, 0)

        near(
            page_box(desktop, desktop.get_by_text("100 S. River Street, Downtown Aurora IL"))["y"],
            529,
        )

    def test_sections_gallery_and_buttons(self, desktop: Page):
        desktop.goto("/")
        headings = [page_box(desktop, h) for h in desktop.get_by_role("heading", level=2).all()]
        near(headings[0]["y"], 1002)
        near(headings[1]["y"], 1702, 8)
        near(headings[2]["y"], 2568, 8)

        for i, photo in enumerate(gallery(desktop).all()):
            b = page_box(desktop, photo)
            near(b["x"], [138, 526, 914][i], 1)
            near(b["y"], 1764, 8)
            near(b["width"], 370, 1)
            near(b["height"], 256, 1)

        enquire = page_box(desktop, desktop.get_by_role("link", name="Enquire About Your Event"))
        near(enquire["width"], 247, 1)
        near(enquire["height"], 40, 0)
        near(enquire["y"], 1484, 8)

        near(desktop.evaluate("document.documentElement.scrollHeight"), 2809, 12)


class TestScrollEffects:
    def test_header_and_footer_stay_put(self, desktop: Page):
        desktop.goto("/")
        desktop.evaluate("window.scrollTo(0, 1200)")
        header = box(desktop.get_by_role("banner"))
        assert (header["y"], header["height"]) == (0, 79)
        footer = box(desktop.get_by_role("contentinfo"))
        assert footer["height"] == 80
        assert footer["y"] + footer["height"] == 900

    def test_hero_photo_moves_at_a_fifth_of_scroll_speed(self, desktop: Page):
        desktop.goto("/")
        photo = desktop.get_by_test_id("hero-photo")
        before = box(photo)["y"]
        desktop.evaluate("window.scrollTo(0, 200)")
        # 200px scrolled x 0.8 = the layer shifted down 160px.
        desktop.wait_for_function(
            "() => document.querySelector('[data-testid=hero-photo]').style.transform"
            ".includes('160px')"
        )
        assert round(before - box(photo)["y"]) == 40

    def test_hero_photo_still_with_reduced_motion(self, desktop: Page):
        desktop.emulate_media(reduced_motion="reduce")
        desktop.goto("/")
        photo = desktop.get_by_test_id("hero-photo")
        before = box(photo)["y"]
        desktop.evaluate("window.scrollTo(0, 200)")
        desktop.wait_for_timeout(100)
        assert round(before - box(photo)["y"]) == 200


class TestPhoneLayout:
    def test_no_sideways_scroll_and_stacked_gallery(self, page: Page):
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto("/")
        overflow = page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        assert overflow <= 0
        lefts = {round(box(photo)["x"]) for photo in gallery(page).all()}
        assert len(lefts) == 1

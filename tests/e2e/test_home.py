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

    def test_book_your_date_button_on_the_hero_goes_to_the_booking_page(self, page: Page):
        page.goto("/")
        button = page.get_by_test_id("hero").get_by_role("link", name="Book Your Date")
        expect(button).to_be_visible()
        expect(button).to_have_attribute("href", "/book/")

    def test_enquire_button_is_replaced_and_email_us_remains(self, page: Page):
        page.goto("/")
        expect(page.get_by_role("link", name="Enquire About Your Event")).to_have_count(0)
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
    """The original content layout, with the info strip height accounted for."""

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

    def test_sections_and_gallery(self, desktop: Page):
        """The original sections keep their layout below the added venue-info strip."""
        desktop.goto("/")
        strip_height = box(desktop.locator(".venue-strip"))["height"]
        headings = [page_box(desktop, h) for h in desktop.get_by_role("heading", level=2).all()]
        near(headings[0]["y"], 1002 + strip_height)
        near(headings[1]["y"], 1638 + strip_height, 8)
        near(headings[2]["y"], 2532 + strip_height, 8)

        for i, photo in enumerate(gallery(desktop).all()):
            b = page_box(desktop, photo)
            near(b["x"], [138, 526, 914][i], 1)
            near(b["y"], 1700 + strip_height, 8)
            near(b["width"], 370, 1)
            near(b["height"], 256, 1)

        near(
            desktop.evaluate("document.documentElement.scrollHeight"),
            2773 + strip_height,
            12,
        )

    def test_book_button_is_large_centred_and_visible_without_scrolling(self, desktop: Page):
        desktop.goto("/")
        button = box(desktop.get_by_role("link", name="Book Your Date"))
        near(button["x"] + button["width"] / 2, 720, 1)  # centred on the page
        assert button["height"] >= 48  # larger than the 40px buttons elsewhere
        assert button["y"] + button["height"] <= 900 - 80  # above the pinned © bar
        address = box(desktop.get_by_text("100 S. River Street, Downtown Aurora IL"))
        assert button["y"] > address["y"] + address["height"]  # under the address


class TestScrollEffects:
    def test_header_and_footer_stay_put(self, desktop: Page):
        desktop.goto("/")
        desktop.evaluate("window.scrollTo(0, 1200)")
        header = box(desktop.get_by_role("banner"))
        assert (header["y"], header["height"]) == (0, 79)
        footer = box(desktop.get_by_role("contentinfo"))
        assert footer["height"] == 80
        assert footer["y"] + footer["height"] == 900

    def test_hero_photo_stays_fixed_while_the_page_scrolls(self, desktop: Page):
        desktop.goto("/")
        photo = desktop.get_by_test_id("hero-photo")
        before = box(photo)["y"]
        desktop.evaluate("window.scrollTo({top: 200, behavior: 'instant'})")
        assert desktop.evaluate("window.scrollY") == 200
        assert round(box(photo)["y"] - before) == 0
        assert photo.evaluate("el => getComputedStyle(el).transform") == "none"

    def test_hero_photo_is_fixed_with_reduced_motion(self, desktop: Page):
        desktop.emulate_media(reduced_motion="reduce")
        desktop.goto("/")
        photo = desktop.get_by_test_id("hero-photo")
        before = box(photo)["y"]
        desktop.evaluate("window.scrollTo(0, 200)")
        assert desktop.evaluate("window.scrollY") == 200
        assert round(box(photo)["y"] - before) == 0


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

    def test_book_button_fits_inside_the_hero(self, page: Page):
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto("/")
        hero = box(page.get_by_test_id("hero"))
        button = box(page.get_by_role("link", name="Book Your Date"))
        assert button["x"] >= hero["x"]
        assert button["x"] + button["width"] <= hero["x"] + hero["width"]
        assert button["y"] + button["height"] <= hero["y"] + hero["height"]

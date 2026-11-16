"""Content stays visible while motion runs and while deferred scripts are loading."""

from playwright.sync_api import Page, expect

VISIBLE_FRAMES = """() => {
  window.__frames = [];
  const record = () => {
    const selector = 'main h1, .hero__photo, [data-motion], .calendar';
    const targets = [...document.querySelectorAll(selector)];
    for (const element of targets) {
      const rect = element.getBoundingClientRect();
      if (rect.bottom <= 0 || rect.top >= innerHeight) continue;
      let opacity = 1;
      for (let parent = element; parent; parent = parent.parentElement) {
        opacity *= Number(getComputedStyle(parent).opacity);
      }
      window.__frames.push({opacity, clip: getComputedStyle(element).clipPath});
    }
    requestAnimationFrame(record);
  };
  requestAnimationFrame(record);
}"""


def assert_visible_frames(page):
    samples = page.evaluate("window.__frames")
    assert len(samples) > 10
    assert all(sample["opacity"] == 1 for sample in samples)
    assert all(sample["clip"] == "none" for sample in samples)


def test_landing_content_never_disappears_during_entry_or_scroll(page: Page):
    page.add_init_script(f"({VISIBLE_FRAMES})();")
    page.goto("/", wait_until="domcontentloaded")
    page.wait_for_function("window.__frames.length > 20")
    assert_visible_frames(page)
    page.locator(".setting").scroll_into_view_if_needed()
    page.wait_for_function("window.__frames.length > 60")
    assert_visible_frames(page)


def test_mobile_navigation_is_collapsed_before_deferred_scripts(page: Page):
    # A slow script download must not show an expanded menu and then collapse the page.
    page.route("**/js/*.js", lambda route: route.fulfill(body="", content_type="text/javascript"))
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/")
    expect(page.get_by_role("button", name="Menu", exact=True)).to_be_visible()
    expect(page.get_by_role("navigation", name="Main navigation")).not_to_be_visible()
    assert page.locator(".site-header").bounding_box()["height"] <= 100


def test_workspace_motion_keeps_content_visible_and_respects_reduced_motion(page, customer_login):
    page.add_init_script(f"({VISIBLE_FRAMES})();")
    page.goto("/book/", wait_until="domcontentloaded")
    page.wait_for_function("window.__frames.length > 20")
    assert_visible_frames(page)
    page.emulate_media(reduced_motion="reduce")
    page.reload()
    assert page.evaluate("document.getAnimations().length") == 0
    expect(page.get_by_role("heading", name="Request a date")).to_be_visible()

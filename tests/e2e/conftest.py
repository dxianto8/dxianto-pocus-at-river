import pytest
from django.contrib.auth import get_user_model
from playwright.sync_api import Page

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "correct-horse-battery-staple"


def pytest_collection_modifyitems(items):
    for item in items:
        if "/e2e/" in str(item.path):
            item.add_marker(pytest.mark.e2e)


@pytest.fixture(scope="session")
def base_url(live_server):
    """Point Playwright's relative URLs at Django's live test server."""
    return live_server.url


@pytest.fixture(autouse=True)
def _live_db(transactional_db):
    """The live server runs in another thread, so tests need real (committed) transactions."""


@pytest.fixture
def admin_user():
    return get_user_model().objects.create_superuser(
        ADMIN_USERNAME, "admin@example.com", ADMIN_PASSWORD
    )


@pytest.fixture
def admin_page(page: Page, admin_user) -> Page:
    """A page already signed in to the Django admin."""
    page.goto("/admin/login/")
    page.get_by_label("Username").fill(ADMIN_USERNAME)
    page.get_by_label("Password").fill(ADMIN_PASSWORD)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url("**/admin/")
    return page


@pytest.fixture
def customer_login(page: Page):
    """Sign a visitor into their own account before exercising the gated booking flow."""
    user = get_user_model().objects.create_user("eventguest", "avery@example.com", ADMIN_PASSWORD)
    page.goto("/account/login/")
    page.get_by_label("Username", exact=True).fill(user.username)
    page.get_by_label("Password", exact=True).fill(ADMIN_PASSWORD)
    page.get_by_role("button", name="Log in", exact=True).click()
    page.wait_for_url("**/account/")
    return user

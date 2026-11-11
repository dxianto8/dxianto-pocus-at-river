import { expect, test, type Locator, type Page } from "@playwright/test";

async function box(locator: Locator) {
  const b = await locator.boundingBox();
  if (!b) throw new Error("element has no bounding box");
  return b;
}

async function boxes(locator: Locator) {
  return Promise.all((await locator.all()).map(box));
}

/** Position on the page (not the viewport), so values compare with the original's measurements. */
async function pageBox(page: Page, locator: Locator) {
  const b = await box(locator);
  const scrollY = await page.evaluate(() => window.scrollY);
  return { ...b, y: b.y + scrollY };
}

const gallery = (page: Page) => page.getByTestId("gallery").getByRole("img");

test.describe("home page content", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("has the venue title and an accessible h1", async ({ page }) => {
    await expect(page).toHaveTitle("HOME | Pocus At River");
    await expect(
      page.getByRole("heading", { level: 1, name: "Pocus at River, weddings & events" }),
    ).toBeVisible();
  });

  test("shows the three section headings in order", async ({ page }) => {
    await expect(page.getByRole("heading", { level: 2 })).toHaveText([
      "Host Your Event at the Historic Pocus Motors Building",
      "Tell Us About Your Event",
      "Get in Touch",
    ]);
  });

  test("uses the original text word for word", async ({ page }) => {
    await expect(page.getByText(/^Say "I do" in one of downtown Aurora's/)).toBeVisible();
    await expect(page.getByText(/so it's worth locking in your date now\.$/)).toBeVisible();
    await expect(page.getByText("100 S. River Street, Downtown Aurora IL")).toBeVisible();
    await expect(page.getByText("© 2026 by Pocus at River")).toBeVisible();
  });

  test("Enquire goes to the booking page and Email Us opens an email", async ({ page }) => {
    await expect(page.getByRole("link", { name: "Enquire About Your Event" })).toHaveAttribute(
      "href",
      "/book",
    );
    await expect(page.getByRole("link", { name: "Email Us" })).toHaveAttribute(
      "href",
      /^mailto:events@pocusatriver\.com\?subject=Event%20Inquiry$/,
    );
  });

  test("links to the venue's social accounts", async ({ page }) => {
    await expect(page.getByRole("link", { name: "Instagram" })).toHaveAttribute(
      "href",
      "https://www.instagram.com/pocusatriver",
    );
    await expect(page.getByRole("link", { name: "Facebook" })).toHaveAttribute(
      "href",
      "https://www.facebook.com/pocusatriver",
    );
  });

  test("gallery has three photos with alt text", async ({ page }) => {
    await expect(gallery(page)).toHaveCount(3);
    for (const photo of await gallery(page).all()) {
      await expect(photo).toHaveAttribute("alt", /\S/);
    }
  });
});

// Measurements taken from the original site at 1440x900 on 2026-11-11.
test.describe("desktop matches the original (1440x900)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  const near = (actual: number, expected: number, tolerance = 4) =>
    expect(Math.abs(actual - expected), `${actual} should be within ${tolerance}px of ${expected}`).toBeLessThanOrEqual(tolerance);

  test("hero, badge and address sit where the original has them", async ({ page }) => {
    await page.goto("/");
    const hero = await pageBox(page, page.getByTestId("hero"));
    near(hero.x, 80, 0);
    near(hero.y, 79, 0);
    near(hero.width, 1280, 0);
    near(hero.height, 821, 0);

    const badge = await pageBox(page, page.getByRole("heading", { level: 1 }).getByRole("img"));
    near(badge.x, 597, 1);
    near(badge.y, 235, 1);
    near(badge.width, 245, 0);

    const address = await pageBox(page, page.getByText("100 S. River Street, Downtown Aurora IL"));
    near(address.y, 529);
  });

  test("sections, gallery and buttons line up with the original", async ({ page }) => {
    await page.goto("/");
    const headings = await Promise.all(
      (await page.getByRole("heading", { level: 2 }).all()).map((h) => pageBox(page, h)),
    );
    near(headings[0].y, 1002);
    near(headings[1].y, 1702, 8);
    near(headings[2].y, 2568, 8);

    const photos = await Promise.all((await gallery(page).all()).map((g) => pageBox(page, g)));
    photos.forEach((p, i) => {
      near(p.x, [138, 526, 914][i], 1);
      near(p.y, 1764, 8);
      near(p.width, 370, 1);
      near(p.height, 256, 1);
    });

    const enquire = await pageBox(page, page.getByRole("link", { name: "Enquire About Your Event" }));
    near(enquire.width, 247, 1);
    near(enquire.height, 40, 0);
    near(enquire.y, 1484, 8);

    const height = await page.evaluate(() => document.documentElement.scrollHeight);
    near(height, 2809, 12);
  });
});

test.describe("scroll effects", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("header stays at the top and the © bar stays at the bottom", async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => window.scrollTo(0, 1200));
    const header = await box(page.getByRole("banner"));
    expect(header.y).toBe(0);
    expect(header.height).toBe(79);
    const footer = await box(page.getByRole("contentinfo"));
    expect(footer.y + footer.height).toBe(900);
    expect(footer.height).toBe(80);
  });

  test("hero photo moves at 20% of scroll speed", async ({ page }) => {
    await page.goto("/");
    const photo = page.getByTestId("hero-photo");
    const before = (await box(photo)).y;
    await page.evaluate(() => window.scrollTo(0, 200));
    await expect.poll(async () => Math.round(before - (await box(photo)).y)).toBe(40);
  });

  test("hero photo stays still when reduced motion is requested", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    const photo = page.getByTestId("hero-photo");
    const before = (await box(photo)).y;
    await page.evaluate(() => window.scrollTo(0, 200));
    await page.waitForTimeout(100);
    expect(Math.round(before - (await box(photo)).y)).toBe(200);
  });
});

test.describe("phone layout (390px)", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("never scrolls sideways and stacks the gallery", async ({ page }) => {
    await page.goto("/");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
    const lefts = (await boxes(gallery(page))).map((b) => Math.round(b.x));
    expect(new Set(lefts).size).toBe(1);
  });
});

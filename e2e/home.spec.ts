import { expect, test, type Locator } from "@playwright/test";

async function boxes(locator: Locator) {
  const all = await locator.all();
  return Promise.all(
    all.map(async (el) => {
      const box = await el.boundingBox();
      if (!box) throw new Error("element has no bounding box");
      return box;
    }),
  );
}

test.describe("home page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("has the venue title and an accessible h1", async ({ page }) => {
    await expect(page).toHaveTitle(/The Coachworks/);
    await expect(
      page.getByRole("heading", { level: 1, name: "The Coachworks, weddings & events" }),
    ).toBeVisible();
  });

  test("shows the three section headings in order", async ({ page }) => {
    const headings = page.getByRole("heading", { level: 2 });
    await expect(headings).toHaveText([
      /Host Your Event at the Historic Coachworks Building/,
      "Tell Us About Your Event",
      "Get in Touch",
    ]);
  });

  test("both enquiry buttons open an email", async ({ page }) => {
    for (const name of ["Enquire About Your Event", "Email Us"]) {
      await expect(page.getByRole("link", { name })).toHaveAttribute(
        "href",
        /^mailto:hello@example\.com/,
      );
    }
  });

  test("gallery has three photos with alt text", async ({ page }) => {
    const photos = page.getByTestId("gallery").getByRole("img");
    await expect(photos).toHaveCount(3);
    for (const photo of await photos.all()) {
      await expect(photo).toHaveAttribute("alt", /\S/);
    }
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

    const lefts = (await boxes(page.getByTestId("gallery").getByRole("img"))).map((b) =>
      Math.round(b.x),
    );
    expect(new Set(lefts).size).toBe(1);
  });
});

test.describe("desktop layout (1440px)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("shows the gallery in one row", async ({ page }) => {
    await page.goto("/");
    const tops = (await boxes(page.getByTestId("gallery").getByRole("img"))).map((b) =>
      Math.round(b.y),
    );
    expect(new Set(tops).size).toBe(1);
  });
});

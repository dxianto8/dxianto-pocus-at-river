# Venue site rebuild: design

- **Date:** 2026-11-11
- **Status:** draft, awaiting review
- **Repo:** `dxianto8/dxianto-pocus-at-river` (public)

## 1. Purpose

A learning and portfolio project. It rebuilds the layout and visual design of
<https://www.pocusatriver.com/> (a one-page Wix site for an event venue) as a
hand-written Next.js + TypeScript + Tailwind project.

The rebuild uses a **made-up venue, newly written text and free-licence photos**.
It is not affiliated with Pocus at River and must not pass for it. The README
says so in its first paragraph.

## 2. Decisions

From the user:

| Topic    | Decision                                                                                   |
| -------- | ------------------------------------------------------------------------------------------ |
| Goal     | Learning / portfolio piece. Placeholder content, not the real venue's text or photos.      |
| Stack    | Next.js (App Router) + TypeScript + Tailwind CSS.                                          |
| Scope    | Same look as the original, plus a real phone layout and accessibility fixes. No extras.    |
| Delivery | New public GitHub repo `dxianto8/dxianto-pocus-at-river`, branch `main`.                   |

Assumptions the user accepted without changes:

- The venue is **"The Coachworks"** in the made-up town of **Millbrook**. Contact
  email is `hello@example.com` (a domain reserved for examples).
- Photos come from Unsplash, which allows free use. Each is credited in the README.
- The Wix chat bubble and Wix branding are left out.

## 3. The original, for reference

Captured 2026-11-11 at 1440px wide. Order from top to bottom:

1. **Top bar.** Small uppercase link on the left ("EXPLORE POCUS AT RIVER").
   Instagram and Facebook icons on the right.
2. **Hero.** A wide photo of a table setting, about 1280×740, inside side
   gutters. In the centre is a round forest-green badge: a large serif "R", with
   "POCUS AT RIVER" curving along the top and "WEDDINGS & EVENTS" along the
   bottom. Below the badge is an italic serif address line in white.
3. **© line.** Small italic grey serif, placed directly under the hero. This is
   a quirk of the original.
4. **About.** Thin vertical divider line, then an italic serif heading with wide
   letter-spacing, then two paragraphs in a centred column about 600px wide, then
   a charcoal button "Enquire About Your Event" (mailto link).
5. **Gallery.** Divider, then the heading "Tell Us About Your Event", then three
   photos in a row (about 370×256 each), then two paragraphs about corporate events.
6. **Contact.** Divider, then the heading "Get in Touch", then a charcoal button
   "Email Us" (mailto link).

Measured styles:

| Token    | Original value                         | Used for                                  |
| -------- | -------------------------------------- | ----------------------------------------- |
| Serif    | `didot-w01-italic`, 14–18px            | Headings, address line, © line            |
| Sans     | `raleway`, 16–20px                     | Body text, top-bar label                  |
| Forest   | `rgb(38, 56, 34)` / `#263822`          | Badge                                     |
| Charcoal | `rgb(54, 54, 54)` / `#363636`          | Buttons, body text                        |
| Stone    | `rgb(96, 94, 94)` / `#605E5E`          | Headings, secondary text                  |
| Mist     | `rgb(232, 230, 230)` / `#E8E6E6`       | Footer border (divider lines use stone at 40% opacity, which matches the original better) |

On phones the original has no phone layout. It shrinks the 980px desktop page
to fit the screen, and the chat bubble covers the content.

## 4. Content mapping

All text in the rebuild is newly written. Only the topics and structure follow
the original.

| Original                                   | Rebuild                                                        |
| ------------------------------------------ | -------------------------------------------------------------- |
| "EXPLORE POCUS AT RIVER"                   | "EXPLORE THE COACHWORKS"                                       |
| Badge: POCUS AT RIVER / R / WEDDINGS & EVENTS | Badge: THE COACHWORKS / C / WEDDINGS & EVENTS              |
| "100 S. River Street, Downtown Aurora IL"  | "12 Mill Street, Millbrook" (made up)                          |
| "Host Your Event at the Historic Pocus Motors Building" | "Host Your Event at the Historic Coachworks Building" |
| Wedding pitch (2 paragraphs)               | New wedding pitch, about the same length: old carriage workshop, brick, tall windows, room for up to 200 guests, walkable town centre |
| "Tell Us About Your Event"                 | "Tell Us About Your Event"                                     |
| Corporate pitch (2 paragraphs)             | New corporate pitch, about the same length: dinners, launches, parties, parking and nearby hotels |
| "Get in Touch"                             | "Get in Touch"                                                 |
| "© 2026 by Pocus at River" (under the hero) | "© 2026 The Coachworks · a fictional venue" (in a real footer) |

## 5. Architecture

Next.js App Router, created with the latest stable `create-next-app`
(TypeScript, Tailwind, ESLint, App Router, no `src/` folder, `@/*` import alias).
Every component is a server component. The page has no client state and makes
no data requests.

```
app/
  layout.tsx          <html lang="en">, fonts, metadata
  page.tsx            builds the page from content + components
  globals.css         Tailwind import + @theme tokens (colours, fonts)
content/
  site.ts             SiteContent type + the one `site` object (all text, links, images)
components/
  TopBar.tsx          label link + social icon links
  Hero.tsx            hero photo, badge, address
  LogoBadge.tsx       SVG badge with text curving along circle paths
  SectionDivider.tsx  thin vertical line (decorative)
  SectionHeading.tsx  <h2> in italic serif with wide letter-spacing
  Button.tsx          link styled as the charcoal button
  Gallery.tsx         three photos, responsive grid
  Footer.tsx          © line
  icons.tsx           Instagram + Facebook inline SVGs
assets/images/        hero.jpg + gallery-1..3.jpg (imported directly, so the build
                      knows their sizes and makes blurred placeholders)
e2e/
  home.spec.ts        Playwright checks (§9)
playwright.config.ts
```

### What each component takes

```ts
TopBar({ label, href, socials })   // socials: { name: "Instagram" | "Facebook"; href: string }[]
Hero({ image, badge, address })    // image: { src: StaticImageData; alt: string }
LogoBadge({ topText, bottomText, monogram, label })
SectionDivider()                   // no props, aria-hidden
SectionHeading({ id, children })
Button({ href, children })
Gallery({ images })                // images: { src: StaticImageData; alt: string }[]
Footer({ text })
```

**How data moves:** `content/site.ts` → `app/page.tsx` → components, all through
props. No component imports content itself, so each one can be read and reused
on its own.

**Fonts.** Both come from `next/font/google` and are exposed as CSS variables
that the Tailwind theme uses:

- **Raleway** (400, 500) for body text, the top bar and buttons. The original
  used Avenir on its buttons; Raleway replaces it, so the page needs only two fonts.
- **Bodoni Moda** (italic 400) replaces Didot, which is not free to use. Both
  belong to the same family of high-contrast serif typefaces.

**Mail links.** Both buttons use
`mailto:hello@example.com?subject=Event%20Inquiry`.

**Social links.** These point to `https://www.instagram.com/` and
`https://www.facebook.com/`, because the venue is made up. They open in a new
tab (`rel="noopener noreferrer"`) and have `aria-label`s.

## 6. Responsive behaviour

| Width    | Behaviour |
| -------- | --------- |
| ≥ 1024px | Matches the original desktop page. Hero up to 1280px wide with side gutters. Text column up to about 600px, centred. Gallery has three photos across. |
| 640–1023px | Hero shrinks with the page and keeps its gutters. Gallery stays three across, with smaller photos. |
| < 640px  | Hero runs edge to edge at about 70% of the screen height. Badge shrinks (about 160px), and the address line wraps. Gallery becomes one column. Text column gets 24px side padding. The top-bar label shrinks, and the icons stay on the right. |

The page must not scroll sideways at any width from 360px up.

## 7. Accessibility

- Landmarks: `<header>` (top bar), `<main>`, a `<section>` with `aria-labelledby`
  for each content block, and `<footer>`.
- The hero badge sits inside the page's only `<h1>`. The badge SVG has
  `role="img"` and `aria-label="The Coachworks, weddings & events"`, so the
  heading has a readable name.
- Every photo has descriptive `alt` text. Decorative dividers are `aria-hidden`.
- Links and buttons get a visible `focus-visible` outline.
- Contrast: charcoal and stone text on white, and white on charcoal buttons,
  each pass WCAG AA (at least 4.5:1).
- The page has no animations.

## 8. Error handling

The page is fully static and loads nothing while running.

- A missing image fails the build, because images are imported directly instead
  of referenced by URL string.
- The mail links have no failure case on our side.
- Content is checked by the `SiteContent` type when the project compiles.

## 9. Testing and verification

**Automated:** `npm run lint`, `npx tsc --noEmit` and `npm run build` all pass.
Then `npx playwright test` runs `e2e/home.spec.ts` against the production server
(`next start`):

1. The page title includes "The Coachworks", and the `<h1>`'s readable name is
   "The Coachworks, weddings & events".
2. The three section headings appear in order: "Host Your Event…", "Tell Us
   About Your Event", "Get in Touch".
3. Both buttons link to an address starting with `mailto:hello@example.com`.
4. The gallery has three images, each with non-empty `alt` text.
5. At 390×844 the page doesn't scroll sideways
   (`scrollWidth <= clientWidth`), and the gallery photos sit in one column
   (all three share the same left edge).
6. At 1440×900 the gallery photos sit in one row (all three share the same top edge).

**By eye:** screenshots of the original and the rebuild side by side, at 1440px
and 390px, shared with the user for review. These are not compared automatically.

## 10. Delivery

- The user creates the empty public repo `dxianto8/dxianto-pocus-at-river`,
  because this session is not allowed to create public repos. It is then
  attached to the session and pushed to on `main`.
- README covers:
  - Disclaimer: "An unofficial practice rebuild of the layout of pocusatriver.com.
    Not affiliated with Pocus at River. The venue, text and contact details here
    are made up."
  - The stack.
  - How to run it (`npm install`, `npm run dev`, `npm test`).
  - Photo credits: each Unsplash photo with its source link. (Photographer names
    couldn't be looked up: unsplash.com blocks automated requests from the build
    session, while its image server does not. The Unsplash License doesn't require credit.)

## 11. Out of scope

Inquiry form, lightbox gallery, CMS, analytics, deployment, dark mode,
animations, and more than one page.

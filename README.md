# The Coachworks: venue site rebuild

> **An unofficial practice rebuild of the layout of [pocusatriver.com](https://www.pocusatriver.com/).
> Not affiliated with Pocus at River. The venue, text and contact details here are made up.**

A one-page website for a fictional wedding and events venue, written by hand in
Next.js, TypeScript and Tailwind CSS. The original is a Wix site. This version
keeps its look (big hero photo, round logo badge, italic serif headings, thin
divider lines) and adds what the original lacks: a proper phone layout and
accessible markup.

## Stack

- [Next.js 16](https://nextjs.org/) (App Router, fully static, server components only)
- TypeScript
- Tailwind CSS 4
- Playwright for end-to-end tests
- Fonts: Raleway (body text) and Bodoni Moda italic (headings, standing in for Didot)

## Run it

```bash
npm install
npm run dev        # http://localhost:3000
```

Other scripts:

```bash
npm run build      # production build
npm run lint       # ESLint
npm run typecheck  # tsc --noEmit
npm test           # builds, starts the production server, runs Playwright
```

The first time you run the tests on a new machine, install the browser:

```bash
npx playwright install chromium
```

## How it's organised

```
app/            layout (fonts, metadata), page, global styles, favicon
components/     one small component per piece of the page
content/site.ts all text, links and photos in one typed object
assets/images/  the four photos (imported directly, so the build knows their sizes)
e2e/            Playwright tests
docs/           design spec
```

To turn this into a site for a different venue, edit `content/site.ts` and swap
the photos in `assets/images/`. The components don't need to change.

## What the tests check

- The page title and the `<h1>` (the logo badge) have the venue name.
- The three section headings appear in order.
- Both buttons open an email to the venue address.
- The gallery shows three photos, each with alt text.
- On a 390px-wide phone the page never scrolls sideways and the gallery stacks into one column.
- On a 1440px-wide screen the gallery sits in one row.

## Photo credits

All four photos come from [Unsplash](https://unsplash.com/) and are used under the
[Unsplash License](https://unsplash.com/license), which allows free use without
credit. The photographers' names couldn't be looked up when the site was built,
so the source files are listed instead:

| File | Source |
| ---- | ------ |
| `hero.jpg` | https://images.unsplash.com/photo-1511795409834-ef04bbd61622 |
| `gallery-table.jpg` | https://images.unsplash.com/photo-1519225421980-715cb0215aed |
| `gallery-toast.jpg` | https://images.unsplash.com/photo-1519671482749-fd09be7ccebf |
| `gallery-hall.jpg` | https://images.unsplash.com/photo-1510076857177-7470076d4098 |

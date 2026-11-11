# Exact match + bookings: design

- **Date:** 2026-11-11
- **Status:** approved in chat, 2026-11-11. Stack changed to Django + Postgres the
  same day (§6, approved in chat). §4, §7 and §8 were updated to match.
- **Supersedes:** the "fictional venue" content decisions in
  `2026-11-11-venue-site-design.md` (§1, §2, §4, §10), and that spec's Next.js
  architecture. Its accessibility and phone-layout rules still apply.

## 1. Decisions (from the user)

| Topic     | Decision |
| --------- | -------- |
| Content   | Built for Pocus at River with the venue's OK. Use the real name, text, photos, email, address and social links. |
| Bookings  | Whole days: one event per date. |
| Approval  | Visitors send a **request**. It is stored as pending and holds the date. The admin confirms or declines it. |
| Database  | Hosted Postgres (Neon) when deployed. |

## 2. Exact match of the original (desktop)

- Every text string is copied word for word. Photos and the logo badge come from
  the venue's Wix media at full size.
- **Sticky header:** 79px, white, stays at the top while scrolling.
- **Sticky footer bar:** 80px, white, pinned to the bottom of the screen at all
  times. It holds "© 2026 by Pocus at River".
- **Hero:** fills the first screen under the header. The photo moves at 20% of
  scroll speed, which was measured on the original: it shifts 40px for every
  200px of scrolling. The effect is turned off when `prefers-reduced-motion` is set.
- Sizes and spacing are measured from the original at 1440×900 and checked by
  laying screenshots of the two pages over each other.

**Deliberate exceptions:**

1. **Fonts.** Didot and Avenir are paid fonts that Wix licenses, so the closest
   free fonts are used instead. Swap them in if the venue owns licences.
2. **Phones.** The original has no phone layout, so phones keep the responsive
   layout from the first build.
3. **Wix chat bubble.** It is a Wix service and is left out. The booking page
   takes over its job.

## 3. Booking page: `/book`

- On the home page, a **"Book Your Date"** button on the hero photo, under the
  address, links to `/book`. It is forest green and larger than the other
  buttons (52px tall, 17px label), with a light edge and shadow so it stands out
  against the photo. It replaced the original's "Enquire About Your Event"
  button, at the user's request on 2026-11-11. Removing that button moves every
  section below the first one up 64px compared with the original. "Email Us"
  still opens an email to `events@pocusatriver.com`.
- **Month calendar.** Each date shows as Available, On hold (a pending request)
  or Booked (confirmed, or blocked by the admin). Past dates, and dates more
  than 24 months ahead, cannot be picked. The public calendar returns only each
  date's status and never any personal details.
- **Request form** (shown after a free date is picked):
  - Name (required)
  - Email (required)
  - Phone (optional)
  - Event type: wedding, corporate or other
  - Guest count, 1–200
  - Message (optional)

  On submit the request is saved as `pending` and the date immediately shows
  "On hold".
- **Picking a date** (added 2026-11-11). `static/js/booking.js` fetches the
  page for that date and swaps in the calendar and request form without a page
  load:
  - The page scrolls smoothly to the form, and the form fades and rises into place.
  - Focus moves to the form's heading.
  - Back reloads the page.
  - With reduced motion, it jumps instead of sliding.
  - Without JavaScript, or if the fetch fails, the date links work as normal page loads.
- **Double bookings.** A partial unique index on `event_date` covers rows whose
  status is `pending`, `confirmed` or `blocked`. If two people submit at once,
  one of them gets a "that date was just taken" message.
- **Spam.** A hidden honeypot field. A submission that fills it is silently dropped.
- "Today" is calculated in the venue's time zone (`America/Chicago`).

## 4. Admin: Django's built-in admin at `/admin/`

- **Login.** Django user accounts (staff users), created with
  `manage.py createsuperuser`. This replaces the shared password from the
  first version of this spec. Django handles sessions, password hashing and
  CSRF.
- **Bookings list.** Filter by status, browse by date, search by name or
  email. Pending requests sort first. "Confirm" and "Decline" are bulk actions.
  Declining frees the date.
- **Edit form.** Change any booking's date, details, status or admin note, or
  add a booking by hand.
- **Calendar view** (a custom page inside the admin). A month grid showing every
  booking, each linking to its edit form. Free dates have "Block" and "Add
  booking" buttons, and blocked dates have "Unblock".

## 5. Data

`bookings` table:

| Column        | Type                 | Notes |
| ------------- | -------------------- | ----- |
| `id`          | uuid, primary key    | |
| `event_date`  | date, not null       | |
| `status`      | enum                 | `pending`, `confirmed`, `declined`, `cancelled`, `blocked` |
| `name`        | text, null           | Null for blocked dates |
| `email`       | text, null           | |
| `phone`       | text, null           | |
| `event_type`  | enum, null           | `wedding`, `corporate`, `other` |
| `guest_count` | integer, null        | |
| `message`     | text, null           | |
| `admin_note`  | text, null           | |
| `created_at`, `updated_at` | timestamptz | |

Partial unique index: `event_date` where status is in
(`pending`, `confirmed`, `blocked`).

## 6. Tech

- **Django 6.1** on Python 3.13, using Django's own tools: templates, forms,
  ORM, migrations and admin. The site has no frontend framework.
  - **Styling:** one plain CSS file.
  - **JavaScript:** only `parallax.js`. The booking calendar is built on the
    server and works without JavaScript.
- **Database:** Postgres through `psycopg` 3. The connection comes from
  `DATABASE_URL` via `dj-database-url`. The partial unique index is a
  `UniqueConstraint` with a `condition`.
- **Settings** come from environment variables: `DJANGO_SECRET_KEY`,
  `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL`. Time zone is
  `America/Chicago`.
- **Production:** Gunicorn, with WhiteNoise serving static files.
- **Local development:** `docker compose up` starts Postgres 17 and Django.

Layout:

```
config/          settings, urls, wsgi
bookings/        model, forms, calendar builder, views, admin, migrations
templates/       base, home, booking page, admin calendar
static/          css/site.css, js/parallax.js, images/
tests/           pytest unit and view tests; tests/e2e/ browser tests
```

## 7. Testing

- **pytest + pytest-django** (run against Postgres):
  - Month-grid builder.
  - Form rules: past dates, more than 24 months ahead, dates already taken,
    honeypot.
  - The unique constraint.
  - The booking view, including a double booking that hits a race.
  - Admin actions and the admin calendar's block and unblock.
- **pytest-playwright** (browser tests against a live test server):
  - Home-page content.
  - Desktop positions matching the original.
  - Sticky bars and parallax.
  - Phone layout.
  - Requesting a date, then seeing it shown as On hold.
  - The same date cannot be requested twice.
  - Admin login is required.
  - Confirming, declining and blocking a date each change the public calendar.
- **ruff** for linting and formatting.

## 8. Deployment (for the user)

Changed to **Vercel + Neon** on 2026-11-11, at the user's request. Vercel now runs Django
directly, and Neon is added from the project's Storage tab.

1. Import the repo into Vercel. Vercel detects Django from `manage.py` and
   installs the dependencies from `pyproject.toml`. Python is pinned to 3.13 in
   `.python-version`.
2. Add Neon from the Storage tab. This sets `DATABASE_URL` (pooled) and
   `DATABASE_URL_UNPOOLED` (direct).
3. Set `DJANGO_SECRET_KEY`. When a custom domain is added, also set
   `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`.
4. Each build runs `scripts/vercel_build.py`. It applies migrations over the
   direct connection, then runs `manage.py ensure_admin`, which creates the first
   admin login from `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_PASSWORD` and
   `DJANGO_SUPERUSER_EMAIL`:
   - It only creates the login if that username doesn't exist; an existing login
     is never changed.
   - The password must pass Django's password rules, or the build fails.
   - The password is never printed.

   The user deletes the password setting after the first sign-in. Vercel runs
   `collectstatic` itself and serves the static files from its CDN.

At runtime on Vercel (`VERCEL=1`):

- `*.vercel.app` hosts are allowed.
- `CONN_MAX_AGE` is 0, so each request opens a fresh, short-lived connection
  through the pooler.
- `DISABLE_SERVER_SIDE_CURSORS` is on, because Neon's pooler runs in
  transaction mode.

The Dockerfile remains usable on container hosts.

## 9. Out of scope

- Email notifications. This is the suggested next step, using a service such as Resend.
- Payments and deposits.
- Custom admin roles and permissions beyond Django's defaults.

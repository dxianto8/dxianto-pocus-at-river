# Exact match + bookings: design

- **Date:** 2026-11-11
- **Status:** approved in chat, 2026-11-11
- **Supersedes:** the "fictional venue" content decisions in
  `2026-11-11-venue-site-design.md` (§1, §2, §4, §10). That spec's architecture,
  accessibility and phone-layout rules still apply.

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

- On the home page, "Enquire About Your Event" keeps its label but links to
  `/book`. "Email Us" still opens an email to `events@pocusatriver.com`.
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
- **Double bookings.** A partial unique index on `event_date` covers rows whose
  status is `pending`, `confirmed` or `blocked`. If two people submit at once,
  one of them gets a "that date was just taken" message.
- **Spam.** A hidden honeypot field. A submission that fills it is silently dropped.
- "Today" is calculated in the venue's time zone (`America/Chicago`).

## 4. Admin page: `/admin`

- **Login.** One shared password, from the `ADMIN_PASSWORD` environment
  variable. A successful login sets a signed, HTTP-only session cookie (JWT
  signed with `SESSION_SECRET`, valid for 7 days). `proxy.ts` sends anyone
  without a valid cookie to `/admin/login`. Every admin server action checks
  the session again.
- **Requests list.** Pending requests come first. Each has Confirm and Decline
  buttons. Declining frees the date.
- **Calendar.** Shows every booking with its details. The admin can:
  - edit a booking (date, details, status);
  - add a booking by hand;
  - block and unblock dates;
  - cancel a booking.

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

- **Database access:** Drizzle ORM. When `DATABASE_URL` is set it connects to
  Neon through `@neondatabase/serverless`. Otherwise it uses PGlite (Postgres
  running inside Node, stored in `.data/`), so running locally and running the
  tests need no database account. Migrations are created with `drizzle-kit`.
- **Writes:** server actions. Input is validated with Zod.
- **Calendar widget:** `react-day-picker`, restyled to match the site.

## 7. Testing

- **Vitest** (unit tests): availability rules (which dates are past, too far
  ahead or taken), form validation, and session token sign/verify.
- **Playwright** (end to end):
  - Request a date, then see it shown as On hold.
  - The same date cannot be requested twice.
  - `/admin` redirects to the login page without a session, and a wrong
    password is rejected.
  - Confirming, declining and blocking a date each change the public calendar.
  - The existing home-page checks still pass.

## 8. Deployment (for the user)

1. Create a free Neon project and copy its connection string.
2. In Vercel, set `DATABASE_URL`, `ADMIN_PASSWORD` and `SESSION_SECRET` (a long
   random string).
3. Run the migrations once with `npm run db:migrate`.

## 9. Out of scope

- Email notifications. This is the suggested next step, using a service such as Resend.
- Payments and deposits.
- More than one admin account.

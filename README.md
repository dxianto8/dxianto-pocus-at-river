# Pocus at River: website and bookings

The website for **Pocus at River**, the event venue in the Historic Pocus Motors
Building, 100 S. River Street, Downtown Aurora IL. Built with Django and Postgres.

The public site (home, Weddings, Corporate, Gallery, Venue, Packages & pricing) and the
signed-in workspace share one design: Playfair Display for headings and dates,
Montserrat for everything else, forest green and walnut with bronze accents on cream
and ivory. Headings stand on their own, without labels above them; buttons are square.

- **Home page.** A full-width photograph of the venue's own hall with the welcome, the venue beside a photograph,
  and the three kinds of occasion as photos with overlapping text cards. An address bar
  sits above the header.
- **Navigation.** Three groups (Events, The venue, Pricing) that drop down on hover, with
  a bronze rule drawn under whatever the pointer is on. They also open on click, and from
  the keyboard (Arrow Down to enter, Escape to close). Without JavaScript they open on hover
  and focus.
- **Booking needs no account.** Anyone can request a date at `/book/`. Email and phone
  are required on every request (signed-in customers' email comes from their account,
  and their phone is remembered). A visitor without an account gets an email receipt
  and can see their confirmation in the same browser; if they then sign up or sign in
  in that browser, the request (and any catering order) becomes theirs. Requests are
  never matched to accounts by email address. Ownership, pending status and package
  snapshots are set on the server.
- **AM, PM or the full day.** A date can hold a morning (AM) booking and an
  afternoon/evening (PM) booking separately; a full day holds both. The calendar marks
  days with one half still open ("AM open" / "PM open"), and the request form offers only
  what is free. An AM booking starts before noon and a PM booking at noon or later.
- **Catering orders.** The request form asks "Do you want to order catering with us?".
  Yes leads straight to `/catering/order/` for that request: pick items and quantities
  from the published menu and see an estimated total. Orders copy the menu prices,
  appear in the admin under **Catering orders** and on the customer's event, and email
  the venue and the customer. No payment is taken on the site; the team confirms the
  order and arranges payment.
- **Customer workspace (`/account/`).** Each customer sees only their own events.
  - *My events:* the next event with a countdown, a "Needs your attention" list
    (unread messages, new documents, tasks due or overdue), and every request with
    status filters.
  - *Request a date:* the calendar marks the customer's own dates and has a month
    jump list.
  - *Each event* has five sections: **Overview** (progress, details, history, add to
    calendar as `.ics`), **Messages** with the venue, a **Checklist** (a starting list
    is created from the event type and date), a **Day schedule**, and **Documents**.
  - Customers can **change the date and details** of a pending request and **cancel**
    a pending or confirmed event themselves. Cancelling frees the date.
  - *Messages:* one inbox across all events, with an unread count in the navigation.
  - *Account:* edit name, email (needs the current password), phone, and whether to
    receive emails; change password.
- **Planning entry.** Plan an event opens signup for new visitors, preserving the
  calendar destination and any selected package/date through signup or login.
  Logged-in visits to `/` open the workspace; `/explore/` shows the venue website.
- **Packages (`/packages/`).** Published packages and prices come from the admin.
  Initial packages contain no invented rates or inclusions; they show "Priced by
  proposal" until staff configure them.
- **Admin (`/admin/`).** Manage requests and availability, packages, and venue
  settings. Opening a booking also shows its conversation (add a row to reply),
  documents (upload a proposal or contract), checklist, day schedule and history.

Photo sources and permissions are documented in [docs/image-sources.md](docs/image-sources.md).
All images are served locally. Coffee imagery is excluded.

## Run it on your Mac (Docker)

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/) running.

1. Start Postgres and the site. The first run takes a few minutes while the
   images build.

   ```bash
   docker compose up --build
   ```

2. Open <http://localhost:8000>.

3. In a second terminal, create your admin login:

   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

4. Sign in at <http://localhost:8000/admin/>.

Code changes reload automatically. Press `Ctrl + C` to stop. Bookings are kept
in a Docker volume between runs. To wipe them:

```bash
docker compose down -v
```

### Tests and linting

```bash
docker compose run --rm web pytest
```

```bash
docker compose run --rm web ruff check .
```

`pytest` covers:

- **Calendar rules:** past dates, the 24-month limit, and which states visitors see.
- **Form checks** and the spam trap.
- **Double-booking protection.**
- **Vercel deploy settings,** the migration build step, and creating the first admin login.
- **Admin actions:** confirm, decline, cancel, block and unblock (full day or one half).
- **Half days:** AM and PM sharing a date, every overlap refused by the database,
  calendar states, times fitting the half, and moving a request between halves.
- **Guests and catering:** booking without an account, required email and phone,
  claiming a request on sign-up or sign-in in the same browser only, catering orders
  with price snapshots and totals, and that nobody else can open them.
- **Browser tests** (Playwright, Chromium), covering:
  - the booking flow and the admin;
  - all public pages from 360px to desktop;
  - signup → booking → customer status dashboard;
  - the login gate, gallery keyboard controls, and no-JavaScript fallbacks.
- **Workspace features:** editing, moving and cancelling requests, messages and
  unread counts, checklist, day schedule, document upload limits, the calendar file,
  profile changes, and that none of it is reachable for another customer's event.
- **Account security:** password validation, CSRF, safe redirects, owner-only
  queries, legacy booking privacy, password resets and one-time tokens.
- **Admin configuration:** package publishing, rates/inclusions, venue settings,
  and preserving pricing snapshots when packages change.

## How bookings work

| Status    | Set by                     | Holds the date? | Visitors see |
| --------- | -------------------------- | --------------- | ------------ |
| Pending   | A visitor's request        | Yes             | On hold (or "AM/PM open" if only one half is held) |
| Confirmed | Admin: "Confirm" action    | Yes             | Booked       |
| Blocked   | Admin: calendar "Block"    | Yes             | Booked       |
| Declined  | Admin: "Decline" action    | No              | Available    |
| Cancelled | Admin "Cancel", or the customer | No         | Available    |

- Each half of a date (AM, PM) can have only one booking that holds it, and a full-day
  booking holds both halves. The database enforces this with one unique index per half,
  so two visitors submitting at the same moment can't both get the same half. The admin
  calendar shows both halves of each day and can block a full day, the AM or the PM.
- Requests are accepted from today up to 24 months ahead. "Today" is based on
  Chicago time.
- The public calendar only ever shows a date's status. Names and contact
  details appear only in the admin.
- **Emails.** The venue's contact address is emailed about new requests, customer
  messages, uploads, changes and cancellations. Customers are emailed when the status
  changes, when staff reply, and when staff share a document, unless they turn emails
  off under Account. Email needs a configured provider (SendGrid or SMTP); without one nothing is
  sent and everything still works inside the workspace and the admin.
- **Documents** are stored in the database (PDF, Word, Excel, text, JPG, PNG; 4 MB
  each), so no file storage needs setting up. No payments are taken on the site.

## Packages, venue settings, and accounts

Deployments run migrations through `scripts/vercel_build.py`. For an existing
local checkout, run `docker compose exec web python manage.py migrate`.
Migrations add account ownership and optional packages to existing bookings without
assigning historical requests to any user. They also create three configurable
starting packages and the singleton Venue settings record.

In **Admin → Event packages**, edit the title, event type, description, USD price,
price unit (per event/hour/person), whether the amount is a starting rate, price
notes, and confirmed inclusions (one per line). Toggle **Is published** to control
public visibility and booking-form availability. Leave the amount blank to show
**Request pricing**. Packages are interests expressed in a request; the venue
still confirms final pricing and inclusions directly. No payment is collected.

In **Admin → Venue settings**, change the venue name, contact email, phone,
address, homepage headline, and pricing introduction/disclaimer. Changes appear
on the public site without a code deployment.

Staff confirm, decline, or cancel requests in the booking admin. Customers see the
new status in My events and get an email. To link a historical
booking, verify the customer's ownership, then set its **Owner** in the admin.
Never match or auto-assign legacy bookings by an unverified email address.

### Email

Set SendGrid or the SMTP variables in `.env.example` in the deployment environment. Password
reset emails are sent through that connection; the reset links expire after one
hour and cannot be reused. Development prints emails to the console. Until an email provider
is configured, production sends no email at all: neither password resets nor the
event notifications described above.

Older exact-match design documents describe the previous site. The pages and
account workflows documented here describe the current `main` site.

## Project layout

```
config/       settings (all from environment variables), URLs
bookings/     Bookings, messages, checklist, schedule, documents, packages, venue
              settings, calendar logic, forms, admin; services.py holds emails and history
accounts/     Customer registration, authentication URLs, the owner-scoped workspace views
templates/    Public pages, account flows, booking pages, admin calendar
static/       site.css (shared), workspace.css, motion.js (animations), site.js, booking.js,
              workspace.js, fonts, images
tests/        pytest tests; tests/e2e/ are the browser tests
docs/         design specs
```

## Deploy on Vercel (with Neon Postgres)

Vercel runs Django directly. It finds `manage.py`, installs the dependencies listed in
`pyproject.toml`, and serves the CSS and images from its CDN. The database is Neon
(hosted PostgreSQL), added from Vercel's **Storage** tab.

1. **Import the project.** In Vercel, choose **Add New → Project** and import
   `dxianto8/dxianto-pocus-at-river`. Vercel detects Django.
   The first deployment fails because there's no database yet. That's expected.
2. **Add the database.** Open the project's **Storage** tab and choose
   **Create Database → Neon**.
   - **Region:** AWS US East (N. Virginia), the same area where Vercel runs the site by default.
   - **Environments:** connect it to all of them.
   - **Preview branching:** turn it on if offered. Each preview deployment then
     gets its own copy of the database.

   This fills in `DATABASE_URL` and `DATABASE_URL_UNPOOLED` for you.
3. **Add your settings.** Under **Settings → Environment Variables**, add these
   four, each for all environments:

   | Variable                    | Value |
   | --------------------------- | ----- |
   | `DJANGO_SECRET_KEY`         | a long random string (see below) |
   | `DJANGO_SUPERUSER_USERNAME` | the username you'll sign in to the admin with |
   | `DJANGO_SUPERUSER_PASSWORD` | your admin password (at least 8 characters, not too common) |
   | `DJANGO_SUPERUSER_EMAIL`    | your email address (optional) |

   To generate the secret key, run this on your Mac and copy the line it prints:

   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(50))"
   ```

   If `python3` isn't installed, `openssl rand -base64 48` works too.

4. **Deploy again.** Go to **Deployments**, open the menu on the latest one and
   choose **Redeploy**. Every deployment runs `scripts/vercel_build.py` before it
   goes live. It applies any new database migrations and, the first time,
   creates your admin login from the settings above.
5. **Sign in, then remove the password setting.** Sign in at
   `https://<your-project>.vercel.app/admin/`. Once that works, delete
   `DJANGO_SUPERUSER_PASSWORD` from the Environment Variables. The login keeps
   working; the password is stored securely in the database. Later deploys never
   change an existing login, so a password you change in the admin stays changed.

   If a deploy fails with "DJANGO_SUPERUSER_PASSWORD isn't strong enough", the
   build log says why. Choose a stronger password and redeploy.

To add more people, sign in and use **Users → Add user**. Tick **Staff status**
so they can sign in, and **Superuser status** if they should be able to do
everything.

### Using your own domain

When you're ready to move `pocusatriver.com` off Wix:

1. Add the domain under **Settings → Domains** and follow Vercel's DNS steps.
2. Add these environment variables, then redeploy:

   | Variable                      | Value |
   | ----------------------------- | ----- |
   | `DJANGO_ALLOWED_HOSTS`        | `pocusatriver.com,www.pocusatriver.com` |
   | `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://pocusatriver.com,https://www.pocusatriver.com` |

`*.vercel.app` addresses are always allowed, so you don't need to list them.

### How it runs on Vercel

- **Connections.** The site connects through Neon's connection pooler and opens a
  fresh database connection for each request, which suits Vercel's short-lived
  functions. Migrations use Neon's direct connection instead.
- **Settings.** Every setting is listed in `.env.example`.
- **Other hosts.** The `Dockerfile` still works on hosts that run containers
  (Render, Railway, Fly.io). Set the same environment variables there.

## Notes

- **Typography.** Playfair Display and Montserrat are self-hosted (variable, Latin)
  under the SIL Open Font License (`static/fonts/*-OFL.txt`). No external font service
  is contacted at runtime.
- **Colour.** White text never sits on the light bronze (#b49a6c, 2.7:1): buttons use
  #8a6d3b (4.8:1) and small labels on cream use #7d6233 (5.3:1).
- **Motion.** The opening block of each page rises in order once fonts are ready; the home
  photograph settles into place and side photographs wipe in; further down, text rises
  and photographs are uncovered as they come into view; the checklist bar fills. Starting
  states are set before the first paint (`templates/includes/motion_flag.html`), so nothing
  is shown and then hidden; anything already on screen is left alone; photographs only move
  once loaded; markers are removed when an entrance ends. The workspace otherwise stays
  still. With reduced motion, or if the script fails to load, pages are simply still.
- **Photography.** Full-width imagery comes from the owner-authorized Society 57
  assets and a separately verified CC0 wedding detail photograph. See
  `docs/image-sources.md` for the individual asset URLs, credits, and permissions.
- **History.** The earlier Next.js version of this site is in the git history
  (commit `947bf87`).

## Walkthroughs, catering, offers, loyalty, and messaging

The current `main` includes appointment requests, admin-published catering menus and recent
stories, dated package offers, configurable event types/questions and start/end times, loyalty
credits/rewards, private post-event feedback, and SendGrid/Twilio messaging support. Stripe and
Toast checkout remain **Not available yet**. No payments are taken.

See [docs/venue-services.md](docs/venue-services.md) for configuration, privacy rules, scheduler
setup, provider environment variables, and activation steps. Reminder sending and loyalty start
disabled until staff configure them; customer SMS and feedback preferences are opt-in.

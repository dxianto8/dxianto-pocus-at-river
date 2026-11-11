# Pocus at River: website and bookings

The website for **Pocus at River**, the event venue in the Historic Pocus Motors
Building, 100 S. River Street, Downtown Aurora IL. Built with Django and Postgres.

The site includes a full-width photographic homepage, Weddings,
Corporate, Gallery, Venue, and Packages & Pricing pages, plus customer accounts.
It pairs upright Libre Caslon Display headings with sans-serif navigation and
body copy, white surfaces, and restrained dark accents.

- **Booking requires an account.** Both GET and POST requests to `/book/` require
  login. Signup preserves the selected date/package destination. Booking ownership,
  contact email, pending status, and package snapshots are set on the server.
- **Customer workspace (`/account/`).** A separate application shell has sidebar
  navigation, owner-scoped event counts and status filters, the event calendar,
  packages, and account settings. Each customer sees only their own requests, status,
  event details, and the package/pricing recorded when they submitted. Staff notes
  are never displayed to customers. Accounts also support login, POST-only logout,
  password changes, and email password recovery.
- **Planning entry.** Plan an event opens signup for new visitors, preserving the
  calendar destination and any selected package/date through signup or login.
  Signup without an explicit destination also opens the calendar. Normal returning
  logins open My events. Logged-in visits to `/` open the workspace; `/explore/`
  remains available for browsing the venue website.
- **Packages (`/packages/`).** Published packages and prices come from the admin.
  Initial packages contain no invented rates or inclusions; they show Request
  pricing until staff configure them.
- **Admin (`/admin/`).** Manage event requests and availability, edit packages and
  pricing, and change venue/contact information in Venue settings.

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
- **Admin actions:** confirm, decline, cancel, block and unblock.
- **Browser tests** (Playwright, Chromium), covering:
  - the booking flow and the admin;
  - all public pages from 360px to desktop;
  - signup → booking → customer status dashboard;
  - the login gate, gallery keyboard controls, and no-JavaScript fallbacks.
- **Account security:** password validation, CSRF, safe redirects, owner-only
  queries, legacy booking privacy, password resets and one-time tokens.
- **Admin configuration:** package publishing, rates/inclusions, venue settings,
  and preserving pricing snapshots when packages change.

## How bookings work

| Status    | Set by                     | Holds the date? | Visitors see |
| --------- | -------------------------- | --------------- | ------------ |
| Pending   | A visitor's request        | Yes             | On hold      |
| Confirmed | Admin: "Confirm" action    | Yes             | Booked       |
| Blocked   | Admin: calendar "Block"    | Yes             | Booked       |
| Declined  | Admin: "Decline" action    | No              | Available    |
| Cancelled | Admin: "Cancel" action     | No              | Available    |

- Each date can have only one booking that holds it. The database enforces this,
  so two visitors submitting at the same moment can't both get the date.
- Requests are accepted from today up to 24 months ahead. "Today" is based on
  Chicago time.
- The public calendar only ever shows a date's status. Names and contact
  details appear only in the admin.
- **Event-status notifications are not sent.** Check the admin for new requests;
  pending requests are listed first.

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

Staff confirm, decline, or cancel requests in the existing booking admin. Customers
see the latest status when opening or refreshing My events. To link a historical
booking, verify the customer's ownership, then set its **Owner** in the admin.
Never match or auto-assign legacy bookings by an unverified email address.

### Password recovery email

Set the SMTP variables in `.env.example` in the deployment environment. Password
reset emails are sent through that connection; the reset links expire after one
hour and cannot be reused. Development prints emails to the console. Until SMTP
is configured, production email recovery will not deliver messages. Event-status
email notifications are not sent; customers use My events and staff coordinate
arrangements directly.

Older exact-match design documents describe the previous site. The pages and
account workflows documented here describe the `dev` redesign.

## Project layout

```
config/       settings (all from environment variables), URLs
bookings/     Bookings, packages, venue settings, calendar logic, forms, views, admin
accounts/     Customer registration, authentication URLs, owner-scoped dashboard
templates/    Public pages, account flows, booking pages, admin calendar
static/       site.css, site.js, booking.js, images
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

- **Typography.** Upright Libre Caslon Display is self-hosted under the SIL Open
  Font License (`static/fonts/OFL.txt`). Body copy and controls use system sans-serif
  fonts. No external font service is contacted at runtime.
- **Motion.** JavaScript adds staggered hero entrances, one-time scroll reveals,
  and gallery/menu transitions. Reduced-motion preferences disable these effects;
  content remains visible without JavaScript. The hero background stays fixed.
- **Photography.** Full-width imagery comes from the owner-authorized Society 57
  assets and a separately verified CC0 wedding detail photograph. See
  `docs/image-sources.md` for the individual asset URLs, credits, and permissions.
- **History.** The earlier Next.js version of this site is in the git history
  (commit `947bf87`).

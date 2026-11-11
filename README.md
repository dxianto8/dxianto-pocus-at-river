# Pocus at River: website and bookings

The website for **Pocus at River**, the event venue in the Historic Pocus Motors
Building, 100 S. River Street, Downtown Aurora IL. Built with Django and Postgres.

It has three parts:

- **Home page (`/`).** A copy of the original Wix site at desktop sizes: the same
  text, photos, spacing, fixed top and bottom bars, and the slow-scrolling hero
  photo. On phones it uses a proper phone layout, which the original lacks.
- **Booking page (`/book/`),** reached from the green **Book Your Date** button on
  the home page's photo. A month calendar showing each date as Available,
  On hold or Booked. Visitors pick a free date and send a request.
- **Admin (`/admin/`).** Django's admin. Staff can review requests, confirm or
  decline them, edit any booking, and use a calendar view to add bookings and
  block or unblock dates.

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

`pytest` runs 97 tests:

- **Calendar rules:** past dates, the 24-month limit, and which states visitors see.
- **Form checks** and the spam trap.
- **Double-booking protection.**
- **Vercel deploy settings,** the migration build step, and creating the first admin login.
- **Admin actions:** confirm, decline, cancel, block and unblock.
- **Browser tests** (Playwright, Chromium), covering:
  - the booking flow and the admin;
  - the home page matching the original's measured positions at 1440px;
  - the fixed bars and the parallax;
  - the phone layout.

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
- **The site does not send emails yet.** Check the admin for new requests;
  pending requests are listed first.

## Project layout

```
config/       settings (all from environment variables), URLs
bookings/     Booking model, calendar logic, request form, views, admin
templates/    home page, booking pages, admin calendar
static/       site.css, parallax.js, images
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

- **Fonts.** The original uses Didot and Avenir, which are paid fonts that Wix
  licenses. This site uses the closest free matches: Bodoni Moda italic and
  Mulish Light. Raleway is the same as the original. If the venue licenses the
  originals, swap them in `templates/base.html` and `static/css/site.css`.
- **Hero photo.** The original file on the Wix site is only 640px wide, so it
  looks soft on large screens, as it does on the original. A larger version of
  the same photo would sharpen it.
- **History.** The earlier Next.js version of this site is in the git history
  (commit `947bf87`).

# Pocus at River: website and bookings

The website for **Pocus at River**, the event venue in the Historic Pocus Motors
Building, 100 S. River Street, Downtown Aurora IL. Built with Django and Postgres.

It has three parts:

- **Home page (`/`).** A copy of the original Wix site at desktop sizes: the same
  text, photos, spacing, fixed top and bottom bars, and the slow-scrolling hero
  photo. On phones it uses a proper phone layout, which the original lacks.
- **Booking page (`/book/`).** A month calendar showing each date as Available,
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

`pytest` runs 78 tests:

- **Calendar rules:** past dates, the 24-month limit, and which states visitors see.
- **Form checks** and the spam trap.
- **Double-booking protection.**
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

## Deploy (Render + Neon)

Vercel doesn't host Django well. [Render](https://render.com/) runs the
included `Dockerfile` as-is.

1. **Database.** Create a Postgres database, either on [Neon](https://neon.tech/)
   (free tier) or in Render. Copy its connection string (`postgres://...`).
2. **Web service.** In Render, choose New → Web Service, connect this GitHub
   repo, and pick the **Docker** runtime.
3. **Environment variables.** Add these:

   | Variable                     | Value |
   | ---------------------------- | ----- |
   | `DATABASE_URL`               | the connection string from step 1 |
   | `DJANGO_SECRET_KEY`          | a long random string (see below) |
   | `DJANGO_ALLOWED_HOSTS`       | your domains, e.g. `pocusatriver.com,www.pocusatriver.com,your-app.onrender.com` |
   | `DJANGO_CSRF_TRUSTED_ORIGINS`| the same with `https://`, e.g. `https://pocusatriver.com,https://www.pocusatriver.com` |

   To generate a secret key:

   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(50))"
   ```

4. **Deploy.** The container applies database migrations every time it starts.
5. **Admin login.** Once it's live, create your login in the live database from
   your Mac. Put your connection string between the quotes:

   ```bash
   docker compose run --rm -e DATABASE_URL='postgres://...' web python manage.py createsuperuser
   ```

   If your Render plan includes the **Shell** tab, you can run
   `python manage.py createsuperuser` there instead.

All settings are listed in `.env.example`.

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

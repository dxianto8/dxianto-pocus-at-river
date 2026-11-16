# Venue services and activation

All features use the existing account gate, owner-scoped workspace, upright serif headings,
river/steel palette, and Django admin. No new third-party package is needed.

| Feature | Where to configure it | Customer route |
| --- | --- | --- |
| Walkthrough appointments | Publish **Walkthrough slots** (Chicago time); confirm/decline **Walkthrough appointments** | `/walkthroughs/`, `/account/walkthroughs/` |
| Catering menu | Publish **Catering items**, grouped by category, with confirmed prices and dietary notes | `/catering/` |
| Packages and deals | **Event packages** and **Package offers** | `/packages/`, `/account/packages/` |
| Custom event types | **Event type options**, including activation and order | Booking and edit forms |
| Extra questions | **Booking questions**; optional/required, type, choices, applicable event types, and order | Booking and edit forms |
| Timing | **Venue settings → Booking questionnaire → Require event times** | Chicago start/end times, same day |
| Recent events | Manually publish **Recent events**, using approved photography and copy | `/recent-events/` and the homepage |
| Loyalty | **Venue settings → Loyalty**, **Loyalty rewards**, **Loyalty credits**, **Reward redemptions** | `/account/loyalty/` |
| Feedback and reviews | **Event feedback** (private), optional **Venue settings → Review URL** | Owner-only feedback on completed events |
| Stripe and Toast | Deliberately unavailable; no checkout, card fields, credentials, or payment requests | `/account/payments/`; notices on packages/catering |

No menu prices, promotions, testimonials, recent-event stories, or rewards were fabricated or
published by migrations. Staff must publish the actual business content. The migration adds
common event-type options; staff can change or archive them. Historical event labels fall back
to the stored code when an option has been deleted. Archive types to retain their labels.

## Email, texts, and scheduling

1. In the deployment environment set `SENDGRID_API_KEY`, `DEFAULT_FROM_EMAIL` (a verified
   SendGrid sender), and `PUBLIC_SITE_URL` (the full HTTPS origin used by customers).
   When the API key is present, the SendGrid backend sends both transactional emails and
   password resets. Without it, the existing SMTP settings remain available. Development
   without a key uses console email.
2. For texts set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM_NUMBER`. Configure
   the number with Twilio for the intended destinations, and set its incoming-message webhook
   to `https://YOUR_DOMAIN/notifications/sms/`. The webhook validates Twilio's signature before
   changing preferences; STOP/UNSUBSCRIBE variants disable app texting. Re-enabling texting
   in the app does not override Twilio's own blocked-recipient state.
3. Set a long random `CRON_SECRET` in Vercel. The included `vercel.json` schedules one daily
   authenticated GET to `/notifications/dispatch/` at 14:00 UTC (8am winter / 9am summer in
   Chicago). Requests without the correct bearer token are rejected, including when no secret
   is configured. No keys or secrets belong in Git or Admin.
4. Turn on **Automated email** and/or **Automated SMS** under **Venue settings**. They start
   **off**. Staff can set the number of days ahead for reminders and the post-event delay.
   Customer account preferences are checked again immediately before sending. Texting and
   feedback invitations are opt-in; email event updates can be turned off.
5. **Scheduled notifications** shows delivery state, attempts, and safe failure summaries.
   Failed sends retry at most three times, at least five minutes apart; staff can requeue failed
   rows after fixing configuration. `sent` means accepted by the provider, not handset/inbox
   delivery. Atomic queue claims and unique recipient/event keys prevent overlapping scheduler
   runs from sending the same row twice. A provider accepting a request before a network
   timeout can still produce an ambiguous result; review provider logs before manually retrying.
   A process interrupted in `sending` is left for staff/provider investigation rather than
   automatically risking a duplicate. Each invocation has a short delivery budget and processes
   at most 100 due messages; monitor the queue if increasing volume.

For a container host, run `python manage.py send_event_notifications` from a trusted scheduled
job instead of Vercel cron. The same command can be run more often if needed. Schedule times
are local 8am on the configured day; actual delivery follows the scheduler's cadence. If it is
not configured, reminders do not run. No live provider credentials or production settings were
changed by this implementation, and no live text/email was sent as part of verification.

Only confirmed events and confirmed future walkthroughs get reminders. Post-event invitations
require a completed confirmed event and the customer's feedback preference. Invites link to a
login-protected, owner-only form. Public reviews are optional and offered equally for every
rating; private comments are never automatically published. The scheduler uses a bounded
catch-up window, so enabling automation does not email the entire historical booking list.

## Loyalty and offers

The loyalty program starts **off**. Set the earning start date and points per completed event,
publish real rewards and their costs, then enable it. Completed confirmed events since that
start date earn one immutable credit each. Pending, cancelled, declined, and future events do
not. Changing the earning rate does not rewrite existing credits. Staff can add signed manual
adjustments with a reason. Requests reserve points under a per-customer database lock;
declining a redemption releases them. Approved/redeemed rewards keep their cost. Rewards are
requests for venue approval, not cash or automatic payment discounts. If a completed event is
later reversed, staff should add an explanatory credit adjustment.

Offers are either percentage or fixed USD reductions, with inclusive validity dates and
published terms. The largest current saving is shown, never stacked, and never below zero.
These are date-of-request offers; additional eligibility belongs in the displayed terms and
written proposal. Packages without confirmed base prices still say Request pricing. Booking
price/title snapshots preserve the requested package even after prices or promotions change.

## Operational notes

- Migrations preserve existing bookings and add optional timing/catering fields and answer
  snapshots. Admin can require times on new/edited requests after enabling the setting.
- Custom answers store both label and value. Archiving a question retains old answers. Changing
  a question's kind/choices can require a customer to answer it again while editing; use a new
  question for a substantial change.
- Walkthroughs reserve a single published slot under a database uniqueness constraint. Cancellation
  releases it. Active slots' start/end times are read-only in Admin; cancel and arrange a new slot
  when a visit needs moving. These appointments do not hold the event calendar.
- Payment integration is intentionally not implemented or activated, per the requested scope.
- Run `python manage.py migrate`, `python manage.py check`, and the complete pytest suite.
  Tests mock provider calls; use a controlled test recipient separately when activating providers.

# ROSKYRO Healthcare OS — Python + FastAPI + MongoDB + Create React App

This is a full re-platform of the ROSKYRO Healthcare OS product onto a
different tech stack, at 1:1 feature parity with the original build:

| | Original | This build |
|---|---|---|
| Backend | Node.js + Express | **Python + FastAPI** |
| Database | PostgreSQL | **MongoDB** (via Motor, the async driver) |
| Frontend | React + Vite | **React + Create React App** |

Every route, permission rule, status-machine, and business calculation from
the original app (all 8 build phases — the three pricing pillars, the
referral network + settlement engine, QR self-booking, the public marketing
site, the super admin panels, everything) has been ported. The original
Node/Postgres/Vite app at `roskyro-healthcare-os/` is untouched and still
works independently — this is a parallel, separate implementation, not a
replacement.

## Important, honest disclosure: MongoDB in this environment

This backend is written in **genuine MongoDB idioms** throughout — real
Motor/PyMongo async calls (`find_one`, `insert_one`, `update_one`,
`find().to_list()`, `find_one_and_update` with `$inc`, etc.). But the
sandbox this was built in has no way to install or reach a real MongoDB
server: there's no `mongod` package available, and `repo.mongodb.org` /
`fastdl.mongodb.org` are both blocked by the sandbox's network allowlist
(which only covers standard package registries).

To make the app actually runnable and testable here, `app/config.py` has a
`USE_MOCK_DB` flag:

- `USE_MOCK_DB=true` (the default in the delivered `.env`) uses
  [`mongomock_motor`](https://pypi.org/project/mongomock-motor/), an
  in-process, API-compatible mock of Motor. No real database — everything
  lives in memory and resets whenever the process restarts. **This is what
  was used to build, seed, and verify every endpoint in this delivery**
  (including full browser walkthroughs — login, dashboards, referrals,
  QR booking, etc. — all captured against this mock).
- `USE_MOCK_DB=false` switches to a real `motor.motor_asyncio.AsyncIOMotorClient`
  pointed at `MONGODB_URI`. Since every query in the codebase already uses
  the standard Motor/PyMongo API, **no application code needs to change** —
  point `MONGODB_URI` at a real MongoDB (Atlas, a self-hosted instance,
  Docker, etc.), set `USE_MOCK_DB=false`, and run `python -m app.seed` once
  to populate it.

One consequence of the mock: it has no persistent storage, so
`app/main.py`'s startup hook re-seeds demo data automatically on every
boot **only** when `USE_MOCK_DB=true`. A real MongoDB is never
auto-seeded on startup (that would silently wipe real data on every
restart) — seed it once, manually.

## Project layout

```
roskyro-fastapi/
  backend/
    app/
      main.py            FastAPI app, CORS, error-shape middleware, router wiring
      config.py           Env vars incl. USE_MOCK_DB
      db.py                Motor/mongomock client + all collections
      auth.py              JWT auth, password hashing, requireAuth/requireRoles/requireInternal ports
      seed.py              Demo data generator (port of server/src/seed.js)
      utils/               plans.py (requirePlan + renewal math), roles.py, pillars.py,
                            audit.py, notify.py, booking.py, ids.py
      routers/              One file per domain, 1:1 with the Node routes/ directory:
                             auth, orgs, partners, referrals, settlements, tasks, dashboard,
                             notifications, approvals, appointments, reviews, reports, plans,
                             patients, queue, followups, billing, whatsapp, settings,
                             booking_settings, public_booking, doctors
    requirements.txt
    .env
  frontend/
    src/                   Ported almost verbatim from the Vite client (same components,
                            pages, lib/api.js, context) — Create React App needed no code
                            changes because the original client never referenced
                            Vite-only APIs (import.meta.env, etc.)
    public/
    package.json           react-scripts, "proxy": "http://localhost:8000" for local dev
    tailwind.config.js / postcss.config.js
```

## Running it

Backend:

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The demo dataset (partner categories, ROSKYRO internal team, four demo
clinics with different pillar subscriptions, five network partners,
referrals across every status, settlements, appointments, reviews,
patients/queue/invoices for the MANAGE pillar, internal team tasks) seeds
itself automatically on boot. Demo password for every seeded account is
`Roskyro@123` — see the console output on startup for the full list of
seeded logins (e.g. `admin@roskyro.com` for the ROSKYRO super admin,
`sunrise.family.clinic@example.com` for a customer owner with every
pillar active).

Frontend:

```bash
cd frontend
npm install
npm start
```

This starts the CRA dev server on port 3000 and proxies `/api/*` requests
to the backend on port 8000 (via the `proxy` field in `package.json`,
same pattern as the original Vite dev-server proxy).

For a production build: `npm run build` in `frontend/`, then serve the
`build/` directory from behind the same origin/reverse-proxy as the API
(the frontend calls `/api/...` as a relative path, exactly like the
original app).

## Multi-doctor / faculty QR self-booking

Real clinics — especially multispeciality hospitals — don't have one
doctor on one fixed schedule; they have several faculty members, each
available on different days, at different times, often at different
consultation fees. The QR self-booking feature was extended to model
this directly, as a new capability on top of this FastAPI/Mongo build
(the original Node/Postgres build is untouched and does not have this
feature):

- **`doctors` collection** — each doctor/faculty member is their own
  document scoped to an org: `name`, `specialty`, `consultation_fee`,
  `slot_duration_minutes`, `capacity_per_slot`, a `weekly_schedule`
  (a list of `{day, open_time, close_time}` entries — `day` is one of
  `mon`..`sun`; a day simply absent from the list means that doctor
  doesn't work that day at all), and `is_active` (soft-delete — doctors
  are deactivated, never hard-deleted, since past appointments still
  reference them by id/name).
- **`app/routers/doctors.py`** — owner-only CRUD (`GET/POST /api/doctors`,
  `PATCH/DELETE /api/doctors/{id}`) for managing the roster from the
  customer app shell's Booking Settings page. `DELETE` deactivates
  rather than deletes.
- **`app/utils/booking.py`** — `day_key_for_date()` resolves a calendar
  date to a weekday key, and `doctor_slots_for_date()` looks up that
  doctor's `weekly_schedule` entry for that weekday and generates slot
  start-times between `open_time`/`close_time` stepped by
  `slot_duration_minutes` — so a doctor's available times differ
  correctly by date automatically, with zero slots on days they're not
  scheduled.
- **`booking_settings` was trimmed** to org-wide-only fields
  (`is_enabled`, `upi_id`, `booking_window_days`); the fields that used
  to be one-per-org (`consultation_fee`, `booking_open_time`,
  `booking_close_time`, `slot_duration_minutes`, `capacity_per_slot`,
  `doctor_name`) moved onto each doctor document instead.
- **Patient flow is now two steps**: `GET /api/public/booking/{orgId}`
  returns the org plus the active doctor roster (name, specialty, fee);
  the patient picks one, then `GET
  /api/public/booking/{orgId}/doctors/{doctorId}/availability` returns
  that specific doctor's open slots (with remaining capacity) for the
  booking window. `POST /api/public/booking/{orgId}/book` now requires
  `doctorId` in the body.
- **Capacity and token counters are now per-doctor**, not per-org:
  `booking_counters` documents are keyed by
  `slot|{orgId}|{doctorId}|{date}|{time}` and
  `token|{orgId}|{doctorId}|{date}` (previously without the doctor
  segment). This means every doctor runs their own independent queue —
  two different doctors can each hold a booking in the identical
  date+time slot, and each gets their own token #1 for their own day,
  while the *same* doctor's *same* slot still correctly enforces
  `capacity_per_slot` via the same atomic `find_one_and_update($inc)`
  pattern used elsewhere in this codebase (see the comment in
  `app/routers/public_booking.py`).
- **Frontend**: `pages/customer/BookingSettings.jsx` gained a "Doctors &
  Faculty" panel (add/edit/deactivate a doctor, with a day-by-day
  schedule builder) above the QR bookings list, which now also shows a
  "Doctor" column. `pages/PublicBooking.jsx` gained a doctor-picker step
  before the date/time picker, with a "← Change doctor" link to go back;
  the confirmation screen shows the doctor's name and specialty
  alongside the token number.
- Verified end-to-end (curl for the API, Playwright for the UI): roster
  fetch, per-doctor availability across a week (correctly empty on days
  a doctor doesn't work), doctor CRUD with schedule validation, and a
  full patient booking walkthrough on a phone-width viewport — plus
  concurrency checks confirming two doctors can hold the same slot
  independently while one doctor's own slot still hits capacity/409 on
  the (capacity+1)th booking.

### Payment-first booking — no "pending" state

Follow-up refinement: a booking is now only ever created — and a token
only ever issued — once the patient has paid. There is no
`payment_status: "pending"` limbo state for QR bookings anymore.

- If a doctor has a consultation fee, the patient flow adds a payment
  step between the date/time form and the actual booking: the "Continue
  to Payment" button shows the clinic's UPI ID and the amount, and only
  the "Maine Payment Kar Diya — Confirm Booking" click actually calls
  `POST /api/public/booking/{orgId}/book`. That call is what creates the
  appointment and assigns the token, with `payment_status` set straight
  to `"paid"` (self-reported at the point of confirmation, the same
  self-report pattern already used for pillar subscription checkout in
  `customer/Plans.jsx`).
- A doctor with no consultation fee (`consultation_fee == 0`) skips the
  payment step entirely and books straight through with
  `payment_status: "not_required"`.
- The success screen's payment block was changed from an amber "Payment
  pending" box to a green "Payment received" receipt, since by the time
  the confirmation screen renders, payment has already happened.
- Verified via curl (a paid doctor's booking now returns
  `payment_status: "paid"` and `payment.collected: true` immediately, a
  free doctor's returns `payment_status: "not_required"` and
  `payment.collected: false`) and via Playwright (the phone-width
  walkthrough shows the new payment step rendering the clinic's UPI ID
  and amount, and the confirmation screen showing "Payment received —
  ₹500" with the correct token number).

## Partner self-service commission rate (Referral Network / CONNECT pillar)

Partners now self-declare the commission (%) they pay a referring business
per completed referral, and that rate is shown publicly in the Partner
Directory — so a business decides who to make their partner based on the
commission the partner itself is offering, not a rate only ROSKYRO
internal staff could see or set.

- **`PUT /api/settlements/my-rate`** (partner-only) creates or updates the
  caller's own `partner`-scope `settlement_rule` (`settlement_type:
  "percentage"`, 0–100). This is the exact same scope the referral
  settlement engine already resolves against on completion
  (`org_partner_pair > partner > org > platform`, see
  `routers/referrals.py`) — no separate resolution logic was needed, a
  partner's self-set rate just becomes their `partner`-scope default.
  ROSKYRO internal team's `POST /api/settlements/rules` still works
  unchanged and can still negotiate a business-specific
  `org_partner_pair` override that outranks a partner's own default.
  `GET /api/settlements/my-rate` returns the partner's current rate (or
  `null` if unset).
- **`GET /api/partners`, `/partners/{id}`, `/partners/me`, and
  `/partners/recommendations`** all now include a
  `commission_rate_percentage` field per partner (`null` if that partner
  hasn't set one), resolved via a small `_commission_rates_for()` helper
  in `routers/partners.py` that batch-queries active `partner`-scope
  percentage rules — no per-partner extra round trip.
- **Frontend**: `pages/partner/Settlements.jsx` gained a "Your Commission
  Rate" card (above the existing Payout UPI card) where a partner sets/
  edits their percentage. `pages/customer/PartnerDirectory.jsx` shows a
  "💰 X% commission per referral" badge on each partner card (or "not set
  by this partner yet"), plus a "Sort: Highest commission first" option
  so a business can compare partners at a glance.
- Scoped to **percentage only** (no flat-fee self-service option) — a
  partner wanting a flat-fee arrangement still needs that set by ROSKYRO
  internal staff via the existing `POST /rules` endpoint, unchanged from
  before this feature.
- This feature is in the FastAPI/Mongo build only, per the same
  build-scope decision as the multi-doctor booking and payment-first
  booking features above — the Node/Postgres build's settlement rules
  remain internal-team-only with no partner self-service or public
  directory display.
- Verified via curl (partner sets 15%, `GET /partners` directory listing
  reflects it immediately, updating again edits the same rule in place
  rather than creating a duplicate, a non-partner role gets 403, a rate
  outside 0–100 gets 400) and via Playwright (the directory shows
  CityScan Diagnostics' seeded 10% rate, sorting by highest commission
  puts it first, the partner's own Settlements page pre-fills their
  current rate and saves an update to 15% which then reflects in the
  directory). `CI=true npx react-scripts build` compiles cleanly.

## Free partner self-listing + curated CONNECT category taxonomy

Any doctor, clinic, or hospital can list itself as a CONNECT partner for
free — listing is never gated behind a paid subscription. Every business
on the platform independently decides which partners to work with; ROSKYRO
never auto-assigns or forces a partnership.

- **Category taxonomy replaced.** The old flat, ad-hoc 14-category list
  (`diagnostics`, `imaging`, `specialists`, `ambulance`, `eye_care`, …) is
  gone. `partner_categories` documents are now seeded from a curated,
  two-level taxonomy — 5 groups, 23 leaf categories, matching CONNECT's
  "Verified Healthcare Service Partners" positioning exactly:
  - 👨‍⚕️ **Specialist Referrals** — Cardiologist, Orthopedic, Gynecologist,
    Pediatrician, Neurologist, Gastroenterologist, ENT Specialist,
    Dermatologist, Urologist, Oncologist, Psychiatrist, Other Specialists
  - 🧪 **Diagnostics** — Blood Test Labs, Pathology Labs, Home Sample
    Collection
  - 🩻 **Imaging** — X-Ray Centers, Ultrasound (USG) Centers, CT Scan
    Centers, MRI Centers
  - 🏃 **Rehabilitation** — Physiotherapy Centers, Rehabilitation Centers
  - 🏠 **Home Healthcare** — Physiotherapy at Home, Elder Care Services

  Each category document now carries `group_slug`/`group_name` alongside
  its own `slug`/`name` (see `CATEGORY_GROUPS` in `app/seed.py`), so the
  frontend can render a grouped `<optgroup>` picker instead of one long
  flat dropdown. This is a curated list, not an open-ended one — a
  category that doesn't fit anywhere in it (ambulance/transport, eye care)
  isn't shoehorned in; the closest seeded demo partners were remapped
  accordingly (e.g. the old "Metro Ambulance Services" demo partner was
  replaced with a cardiology clinic, since ambulance/transport has no home
  in the curated list).
- **Registration is genuinely free.** `POST /api/partners/register`
  already existed but had no frontend UI and sat behind the entire
  `/api/partners` router's `require_plan("connect")` dependency — meaning
  a business without an active CONNECT subscription couldn't even submit a
  free application. The plan gate was moved off the router and onto only
  the three endpoints that actually browse/search the paid directory
  (`GET /partners`, `GET /partners/recommendations`, `GET
  /partners/{id}`); `GET /partners/categories`, `GET /partners/me`, `POST
  /partners/register`, and `PATCH /partners/{id}` are unrestricted by
  plan — any authenticated business user can list themselves.
- **`GET /api/partners/me`** now looks a partner profile up by the caller's
  `org_id` instead of requiring `appShell == "partner"`. A business that
  self-registers stays on its regular customer-shell account (there's no
  separate partner-shell login provisioned as part of self-registration,
  consistent with how ROSKYRO team-verified partners have historically
  been onboarded) — it needs to be able to check its own
  pending/verified application status from that same account.
- **New frontend page**: `pages/customer/BecomePartner.jsx` at
  `/app/become-partner` — a "Become a Partner" nav link under CONNECT that
  is deliberately *not* pillar-gated (unlike the rest of the CONNECT nav
  section, which shows a lock icon without an active subscription). Shows
  a grouped category picker, optional coverage/turnaround/contact/services
  fields, submits to `POST /partners/register`, and once submitted shows
  an "Application submitted" / "You're a verified partner" state instead
  of the form again (detected via `GET /partners/me`).
- **`PartnerDirectory.jsx`** category filter now groups by `group_name`
  via `<optgroup>`, and gained a "List your business — it's free →" link
  to `/app/become-partner`. It also now catches a 402 from the CONNECT
  plan gate and shows an explicit "Activate CONNECT to browse" empty state
  with a link to `/app/plans`, instead of crashing on an unhandled
  request — browsing the full directory is a paid CONNECT feature, but a
  business without that plan can still land on this page (e.g. via the
  sidebar's locked nav item, a stale link, or the back button) and needs a
  graceful message rather than an error screen.
- **Public marketing pages updated** with the CONNECT copy provided for
  this feature: `pages/Landing.jsx` gained the short "Homepage Version" —
  the "🤝 CONNECT / Verified Healthcare Service Partners" blurb plus the 5
  group names as pills. `pages/Services.jsx` gained the fuller version —
  the same blurb plus the complete 5-group/23-category grid, matching
  what a business sees when picking a category on the actual registration
  form, with a "List your business for free" CTA into `/register`.
- This feature is in the FastAPI/Mongo build only, per the same
  build-scope decision as the multi-doctor booking, payment-first booking,
  and partner commission rate features above — the Node/Postgres build is
  untouched.
- Verified via curl (categories endpoint returns the new grouped taxonomy;
  a customer-shell org with **no** CONNECT plan gets `402` on `GET
  /partners` but `201` on `POST /partners/register`, proving the paid
  directory and free registration are gated independently; `GET
  /partners/me` returns the newly-created profile for that same
  customer-shell account) and via Playwright (the Become a Partner form
  renders 5 optgroups, submits, and persists the "already applied" state
  across a reload; the Partner Directory shows a graceful upgrade prompt
  instead of a crash for a non-CONNECT account, and shows 5 optgroups plus
  the remapped category names for a CONNECT-enabled account; the Landing
  and Services pages render the provided CONNECT copy). `CI=true npx
  react-scripts build` compiles cleanly.

## Two-sided settlement confirmation (payer claims, payee confirms)

A referring business's own "I've Paid" click was never, by itself, enough
to finalize a settlement — but the previous implementation quietly
finalized it anyway. This closes that gap: the payer's claim and the
payee's confirmation are now two independent steps, and only the second
one moves a settlement out of `pending`.

- **`POST /api/settlements/{id}/mark-paid`** (the referring/payer
  business) no longer flips `status` to `"paid"`. It now only records
  `payer_marked_paid_at` on the settlement and leaves `status` at
  `"pending"`. Calling it twice on the same settlement is rejected with
  `400` ("Already marked paid — waiting for the partner to confirm
  receipt.").
- **`POST /api/settlements/{id}/confirm-received`** (new, partner-only) —
  the receiving partner independently confirms the money actually
  arrived. Only this call sets `status: "paid"` and `paid_at`. It's
  rejected with `400` if the payer hasn't claimed payment yet (nothing to
  confirm), `403` if the caller isn't the partner this settlement is
  owed to (checked by `org_id`, not just "any partner"), and `400` again
  if the settlement is already confirmed.
- **ROSKYRO internal staff's `mark-paid`** is the one exception — it's a
  dispute-resolution override (a business reported the payment through
  support instead of using the app) and finalizes the settlement to
  `"paid"` immediately, bypassing the partner-confirmation step, since
  internal staff are vouching for the payment rather than self-reporting
  it. A payer-org's own `mark-paid` call is never treated this way.
- **Frontend**: `pages/customer/Settlements.jsx` — after clicking "I've
  Paid — Mark Paid", the action cell switches to "Waiting for partner to
  confirm receipt" instead of the button, and the `status` badge stays
  "pending" (not "paid") until the partner acts.
  `pages/partner/Settlements.jsx` gained a new "Awaiting your
  confirmation" stat tile (highlighted with an amber ring when non-zero)
  and a "Confirm Received" button per settlement the payer has claimed —
  clicking it calls the new endpoint and the row flips to "paid".
  `pages/internal/Settlements.jsx` gained a "Business claims paid" column
  showing `payer_marked_paid_at` for oversight, and its "Mark Paid" button
  was relabeled "Mark Paid (override)" with updated copy explaining it
  bypasses the normal two-sided flow.
- `app/seed.py`'s settlement documents now carry `payer_marked_paid_at`
  and `confirmed_by` alongside the existing `status`/`paid_at` fields.
  One seeded settlement (Vital Skin & Aesthetics → CityScan Diagnostics,
  for the Kavita Iyer referral) is seeded with `payer_marked_paid_at`
  already set, so the partner's "Confirm Received" button has a live
  demo target immediately after seeding; every other seeded settlement is
  fully untouched (`payer_marked_paid_at: null`), demoing the "nothing
  done yet" state.
- Verified via curl: a fresh settlement's `confirm-received` correctly
  rejects with `400` before the payer has claimed; the payer's
  `mark-paid` leaves `status: "pending"` and sets
  `payer_marked_paid_at`; a second `mark-paid` call correctly `400`s; the
  wrong partner's `confirm-received` correctly `403`s; the owed partner's
  `confirm-received` correctly finalizes to `status: "paid"`; a second
  `confirm-received` correctly `400`s; internal's `mark-paid` override
  finalizes a completely untouched settlement to `"paid"` in one call, no
  partner action needed. Verified via Playwright end-to-end across all
  three shells: customer claims payment → sees "Waiting for partner to
  confirm receipt" with the status badge still "pending"; partner sees
  the "Awaiting your confirmation: 2" tile and two "Confirm Received"
  buttons, confirms both, tile drops to 0 and both rows show "paid";
  customer reloads and now sees "paid"; internal oversight view shows
  both settlements' "Business claims paid" timestamps and final "paid"
  status. `CI=true npx react-scripts build` compiles cleanly.

## Patient WhatsApp notifications (referral lifecycle)

The patient has no ROSKYRO login and never opens the app — before this,
there was genuinely no way for them to find out where or to whom they'd
been referred. `referral_documents` inserted a `referral_slip`/`qr_code`
DB record on every referral, but the `file_url` pointed at a path
(`/generated/referral-slips/{code}.pdf`) that was never actually
generated, served, or sent anywhere — pure unreachable metadata.

- `app/routers/referrals.py` gained `_notify_patient_whatsapp(referral,
  event)` — a simulated WhatsApp send (same "no real WhatsApp Business
  API in v1" simulation as `routers/whatsapp.py`) that builds a
  Hinglish message naming the partner, their city, their contact phone,
  the service, and the referral code, and inserts it as a genuine
  outbound `whatsapp_messages` row scoped to the *referring* business's
  `org_id` (so it also shows up in that business's own WhatsApp
  Communication log at `/app/whatsapp`, not just buried in the referral).
  Silently no-ops if the referral has no `patient_phone` on file — never
  blocks the referral flow.
- Wired into the lifecycle at the four points that actually matter to a
  patient: `create_referral` fires it immediately when a referral goes
  straight to `"sent"` (no review needed); `transition_referral` fires it
  again for `"sent"` (covers a referral released from `pending_review`,
  so the patient is told the moment it actually reaches the partner —
  not double-sent for the already-notified path), `"accepted"`,
  `"report_uploaded"`, and `"completed"`. A referral that gets
  `"declined"` after being sent still shows the original `"sent"`
  message (the patient was told before it was declined) but nothing
  further — declining is a business-side matter, not something pushed to
  the patient.
- `GET /api/referrals/{id}` now also returns `patient_notifications` — the
  full list of what was actually sent to the patient's phone, in order.
  `pages/shared/ReferralDetail.jsx` (used by all three shells) renders
  this as a new "Patient Notifications" card, so both the referring
  business and the partner can see exactly what the patient was told and
  when, without either side having to separately confirm it.
- `app/seed.py` now seeds the same notifications for every seeded
  referral, driven off the same `history_steps` list already used to
  seed status history — a completed referral gets all four messages, a
  declined one gets only the "sent" message, a `pending_review` referral
  (not yet released to the partner) gets none.

**Verified end-to-end:** curl confirmed a completed referral (Ramesh
Pawar → CityScan Diagnostics) has all four seeded messages in order with
correct content; a `pending_review` referral (HomeCare Plus) has zero
notifications; a `declined` referral (Rahul Menon) has only the `sent`
message; creating a brand-new live referral immediately produced a
`referral_sent` WhatsApp message with the correct partner name, city,
phone, and referral code. Playwright confirmed the "Patient
Notifications" card renders identically and correctly on both the
referring business's and the partner's referral detail pages, with zero
console/page errors. `CI=true npx react-scripts build` compiles cleanly.

## Public marketing site — full site structure

The public marketing pages went from four thin pages to a full
business-objective-driven site structure, on the principle that a website
shouldn't just be a collection of pages — every page should have a clear
job. All of it lives under `frontend/src/pages/` (public pages sit
directly under `pages/`, legal pages under `pages/legal/`) and is wired in
`App.jsx`.

- **Homepage (`Landing.jsx`)** — hero with "Get Free Consultation" /
  "Book Demo" CTAs, Trusted By strip, the three GROW/MANAGE/CONNECT
  pillar cards (now with their sub-feature bullets inline), a "Why
  ROSKYRO" 6-tile grid, a 4-step "How ROSKYRO Works" timeline, an
  Industries We Serve pill list, an 8-question FAQ preview (linking to
  the full FAQ page), and a closing CTA. Success-numbers and
  testimonials sections were intentionally left out of this pass — there
  is no real usage/review data yet to populate them with honestly; add
  them once real numbers exist rather than shipping placeholder stats.
- **About Us (`About.jsx`)** — restructured into Our Story, Our Vision,
  Our Mission (4 points), Our Core Values (Trust/Innovation/
  Transparency/Growth/Customer First — 5 cards), Why Choose Us, a
  5-step "Meet Our Process" timeline (Discovery → Planning →
  Implementation → Optimization → Growth), and a closing CTA. The
  original "How we operate" content (AI-reviewed-by-human, transparent
  payments, no lock-in) is preserved as-is inside Our Mission/Core
  Values rather than deleted, since it's real product behavior, not
  marketing filler.
- **Services (`Services.jsx`)** — kept the existing plan-driven pillar
  sections (pulled live from `GET /plans`), and added a static
  "What's Inside Each Pillar" breakdown (AI Visibility Management /
  Google Business Profile / Review Growth / Digital Marketing sub-groups
  for GROW, etc.) plus an Industries We Work With strip and a two-button
  See Plans / Book Demo closing CTA.
- **Pricing (`Pricing.jsx`)** — added an Enterprise/custom-pricing
  callout (routes to Contact with `?reason=enterprise`), a pricing-specific
  FAQ, and a "Book Free Demo" closing CTA.
- **Contact Us (`Contact.jsx`, new)** — a real lead-capture form (name,
  phone, email, business name, business type, city, message) posting to
  a new public endpoint, an office-details card, a WhatsApp deep link,
  and an embedded Google Map. Reads `?reason=` from the query string
  (`demo`, `consultation`, `enterprise`, `general`) set by whichever CTA
  the visitor clicked, and tags the submitted lead with it.
- **FAQ (`FAQ.jsx`, new)** — standalone page rendering the full FAQ set;
  the Homepage preview and this page share one data source
  (`src/data/faq.js`) so the two never drift out of sync.
- **Legal pages (`pages/legal/`, all new)** — Privacy Policy, Terms &
  Conditions, Refund Policy, Cookie Policy, Disclaimer. Content is
  realistic, healthcare-SaaS-appropriate standard boilerplate covering
  the sections a business of this kind actually needs (data collection,
  refund eligibility, governing law, no-medical-advice disclaimer,
  etc.) — every page carries a small honest footnote that it's
  AI-drafted standard-form content, not a substitute for a lawyer's
  review before being treated as legally binding.
- **Footer (`components/PublicNav.jsx`)** — rebuilt from a one-line
  copyright strip into the full structure: Company / Solutions /
  Industries / Contact columns, a social-links row (placeholder `#`
  hrefs — no real social profiles exist yet, so these intentionally
  don't point anywhere fake), a working newsletter signup, and a bottom
  bar with the legal-page links. The header nav gained a "Contact Us"
  link alongside Home/Services/Pricing/About Us.

**New backend, minimal and honest about its own scope:**
`app/routers/public_marketing.py` adds two unauthenticated endpoints (same
"no login exists yet for this visitor" pattern as `public_booking.py`):
`POST /api/public/contact` (validates name + at least one of phone/email,
stores into the new `contact_leads` collection) and `POST
/api/public/newsletter-subscribe` (validates email, de-dupes against
`newsletter_subscribers`). Both are real writes, not decorative UI — a
visitor filling out the Contact form or the footer newsletter box is
actually persisted, not silently dropped. There's no admin review screen
for these leads yet; that's a deliberately separate, later piece of work.

**Contact details:** the WhatsApp number (+91 92441 66752) and social
profile links (Facebook, Instagram, LinkedIn, YouTube, Google Business
Profile) are real, supplied by the user and wired into both
`components/PublicNav.jsx`'s footer and `pages/Contact.jsx`'s
office-details card. X/Twitter has no handle yet (`href="#"`). The email
(`hello@roskyro.com`), registered office address (Mumbai, Maharashtra —
no street address given), and business hours are still placeholders —
replace those with the real details before going live.

**Verified:** Playwright screenshots of all 12 public routes (Home,
About, Services, Pricing, Contact ×2 reasons, FAQ, and all 5 legal
pages) with zero page errors; an end-to-end Contact form submission
(fill → submit → success state) and a footer newsletter submission
(fill → subscribe → "you're subscribed" state) both confirmed against
the live backend. `python3 -c "import app.main"` imports cleanly with
the new router registered.

## Mobile-number login + manual, by-hand password reset

Every login-capable account — super admin, internal staff, a customer
org's owner/doctor/staff, a partner admin — now signs in with **either
their mobile number or their email**, plus their password. There is no
self-service "forgot password" email link in v1 (no real outbound
email/SMS provider is wired up); instead, a locked-out user submits a
request naming themselves, and only ROSKYRO's super admin can see the
queue and set a new password by hand.

- `app/utils/phone.py`'s `normalize_phone()` strips everything but digits
  and keeps the last 10, so "9800000001", "+91-9800000001",
  "+91 98000 00001" and "09800000001" all match the same stored `phone`
  value — a user can type their number however they like.
- `POST /api/auth/login` takes a single `identifier` field (not separate
  `email`/`phone` fields): a bare `@` check decides whether to look it up
  as an email (existing case-insensitive regex match) or a mobile number
  (normalized suffix match). `POST /api/auth/register` now requires
  `phone` (previously optional) and rejects both a duplicate email and a
  duplicate mobile number — every new self-registered owner needs a
  working login identifier from day one. `POST /api/orgs/{id}/team`
  (a business owner inviting staff) got the same required-phone +
  duplicate-check treatment for consistency.
- `POST /api/password-resets` (public, no auth) — the "bhool gaya
  password" request: give your mobile number or email, optionally a note
  ("naya phone liya", etc.). Resolves the user the same way login does,
  and is idempotent — resubmitting while a request is already pending
  returns the existing one instead of piling up duplicates. Deliberately
  vague on "no account found" (no user enumeration), same tone as a
  failed login.
- `GET /api/password-resets` and `POST /api/password-resets/{id}/resolve`
  / `.../dismiss` are **super-admin only** (`roskyro_admin` — same
  precedent as Pricing & Payments in Phase 4, not every internal role).
  `resolve` takes a `newPassword` the admin typed or generated, hashes it
  onto the target user, and marks the request resolved — this is the "super
  admin apne hand se ye sab kar k dega" step: nothing here is automatic,
  no email/SMS is actually sent, the admin is expected to call/WhatsApp
  the user with the new password themselves.
- Frontend: `Login.jsx`'s single "Mobile number or email" field replaces
  the old email-only input, with a "Forgot password?" link that expands
  an inline request form (no page navigation) and shows a clear
  "this is not automatic" confirmation once submitted. `Register.jsx` and
  `customer/Team.jsx` both now require the mobile number field with a
  "you'll use this to sign in" hint. `internal/PasswordRequests.jsx`
  (new, `/team/password-requests`, admin-only nav entry) lists
  pending/handled requests; resolving one shows the new password in a
  copyable box with a **"Done — I've told them"** button that only *then*
  reloads the list — the box deliberately doesn't auto-dismiss on its own,
  since the whole point is the admin has time to actually read/relay the
  password before it's gone for good.
- `app/seed.py` now gives every seeded login account (10 internal team
  members, 4 customer owners + 4 referring doctors, 5 partner admins) a
  deterministic sequential mobile number starting at `+91-9800000001`, so
  mobile-number login is demoable immediately after a fresh seed, not
  just email login.

**Bug caught and fixed during verification:** the first version of the
admin's "Reset Password" action called the list-reload immediately after
a successful reset, which re-rendered the request into the "Handled"
section — unmounting the very box showing the freshly generated password
before the admin could read it. Caught via a Playwright check that
specifically re-read the page *after* the reload settled (not just right
after the click) and found the password text gone. Fixed by decoupling
the reload from the resolve action — the list only refreshes once the
admin clicks "Done," which is also the more honest UX: the reload
shouldn't happen until they've actually relayed the password.

**Verified end-to-end:** curl covered every path — mobile login with
three different input formats, wrong-password rejection with the new
mobile-aware error message, register rejecting both a missing and an
invalid phone plus a duplicate-phone conflict, the full
submit → idempotent-resubmit → super-admin-list → weak-password-rejected
→ resolve → old-password-now-fails → new-password-works →
resolve-twice-rejected chain, and an ops manager (non-super-admin)
correctly getting 403 on every password-resets endpoint. Playwright
confirmed the same end-to-end on the real running frontend: mobile-number
sign-in lands in the right app shell, the Login page's Forgot Password
panel submits and confirms, the super admin's Password Requests page
shows the pending request, the Generate + Reset Password action displays
the new password with zero premature reload, and clicking Done correctly
moves the row to Handled with zero console/page errors throughout.
`CI=true npx react-scripts build` compiles cleanly.

## What's identical to the Node/Postgres build

- Every API route, request/response shape, and error message (`{ "error":
  "..." }`, including the richer `requiredPillar`/`upgradeRequired` 402
  shape from `requirePlan`).
- The referral status machine, per-transition authorization rules, and the
  settlement-rule resolution order (`org_partner_pair` > `partner` > `org`
  > `platform`).
- The "ROSKYRO never touches referral commission money" model — settlements
  are still a direct B2B UPI payment tracked by the app, not processed by it.
- QR self-booking: sequential per-day token numbers and per-slot capacity
  enforcement. Postgres used `SELECT ... FOR UPDATE` row locks inside a
  transaction; Mongo transactions need a replica set (unavailable with the
  sandbox's mock client), so this uses atomic `find_one_and_update($inc)`
  counter documents instead — still race-safe under concurrent bookings,
  just via a different (equally standard) Mongo pattern. See the comment in
  `app/routers/public_booking.py`.
- Three pricing pillars (GROW / MANAGE / CONNECT) plus the Complete bundle,
  `requirePlan`-style gating, and the super-admin-only plan/pricing editor.
- Audit logging on every state-changing endpoint (best-effort, never blocks
  the primary request — same as the original).

## What's structurally different (Mongo vs. Postgres), by design

- IDs are string UUIDs used as Mongo's `_id` (not `ObjectId`), so the API
  response shape is byte-for-byte compatible with what the existing React
  frontend expects — no `id`/`_id` translation layer needed anywhere.
- SQL `JOIN`s (referrals across 5 tables, partners across 3, the org list's
  `LATERAL` pillar/revenue aggregation) are replaced with explicit
  multi-query "manual joins" in application code — fetch related documents
  by id and merge them in Python — rather than Mongo's `$lookup`
  aggregation pipeline. This was a deliberate choice for two reasons: it
  keeps the code easy to audit line-by-line against the original SQL, and
  `mongomock`'s aggregation-pipeline support is far less complete than its
  basic CRUD support, so this is also what makes local verification
  possible at all in this sandbox.
- Mongo transactions need a replica set; several original endpoints (org
  registration, referral creation, partner registration) used a single
  Postgres transaction to keep a few inserts atomic. These are now
  sequential best-effort operations with a comment at each call site. On a
  real MongoDB deployment these could be wrapped in a client-session
  transaction with no other code changes.

from app.config import MONGODB_URI, MONGODB_DB, USE_MOCK_DB

if USE_MOCK_DB:
    from mongomock_motor import AsyncMongoMockClient

    client = AsyncMongoMockClient()
else:
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGODB_URI)

db = client[MONGODB_DB]

# Collections — one per domain, mirroring the Postgres tables in the
# original build 1:1 so the port is easy to audit against the Node source.
organizations = db["organizations"]
users = db["users"]
partner_categories = db["partner_categories"]
partners = db["partners"]
partner_services = db["partner_services"]
referrals = db["referrals"]
referral_status_history = db["referral_status_history"]
referral_documents = db["referral_documents"]
referral_followups = db["referral_followups"]
settlement_rules = db["settlement_rules"]
settlements = db["settlements"]
statements = db["statements"]
# Periodic (monthly) payouts ROSKYRO makes to a referring business, equal to
# a fixed % of the Marketing Fees collected from partners on that
# business's completed referrals during the period. See
# app/routers/settlements.py's marketing-fee-report / marketing-payouts
# endpoints.
marketing_payouts = db["marketing_payouts"]
appointments = db["appointments"]
reviews = db["reviews"]
marketing_performance = db["marketing_performance"]
visibility_score_history = db["visibility_score_history"]
approvals = db["approvals"]
notifications = db["notifications"]
tasks = db["tasks"]
team_performance = db["team_performance"]
reports = db["reports"]
audit_logs = db["audit_logs"]
plans = db["plans"]
organization_subscriptions = db["organization_subscriptions"]
platform_settings = db["platform_settings"]
booking_settings = db["booking_settings"]
patients = db["patients"]
queue_entries = db["queue_entries"]
patient_followups = db["patient_followups"]
invoices = db["invoices"]
whatsapp_messages = db["whatsapp_messages"]
partner_agreements = db["partner_agreements"]
# Faculty/doctor roster for multi-doctor QR self-booking (multispeciality
# clinics/hospitals) -- each doctor carries their own weekly recurring
# schedule, consultation fee, and slot settings. See app/routers/doctors.py.
doctors = db["doctors"]

# Public marketing-site lead capture -- the Contact Us form and the footer
# newsletter box are both unauthenticated (a visitor has no ROSKYRO account
# yet), so these two collections are written to directly from
# app/routers/public_marketing.py with no auth required, same pattern as
# public_booking.py.
contact_leads = db["contact_leads"]
newsletter_subscribers = db["newsletter_subscribers"]

# "Bhool gaye password" flow (see app/routers/password_resets.py): a user
# who can't sign in submits a request naming themselves; only ROSKYRO's
# super admin can see the queue and actually set a new password ("super
# admin apne hand se ye sab kar k dega") -- there is no self-service
# email-link reset in v1.
password_reset_requests = db["password_reset_requests"]

# Not a Postgres table in the original schema -- an internal helper used to
# replace SQL "SELECT ... FOR UPDATE" row-locking (which needs a replica-set
# transaction in Mongo, unavailable with the sandbox's mongomock client)
# with atomic single-document $inc counters for QR-booking slot capacity and
# token sequencing. See app/routers/public_booking.py.
booking_counters = db["booking_counters"]

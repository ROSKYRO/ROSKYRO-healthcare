"""Seeds realistic demo data: partner categories, a handful of healthcare
businesses (some of which are also network partners), the full internal
ROSKYRO team roster, referrals across every status in the workflow,
settlements, appointments, reviews, marketing numbers, tasks and more.

Direct port of server/src/seed.js. Safe to re-run (it clears every
collection first). Run with:

    python3 -m app.seed
"""
import asyncio
import itertools
import random
from datetime import datetime, timedelta, timezone

from app.db import (
    organizations, users, partner_categories, partners, partner_services,
    referrals, referral_status_history, settlement_rules,
    settlements, appointments, reviews, marketing_performance,
    visibility_score_history, approvals, notifications, tasks, reports,
    audit_logs, plans as plans_collection, organization_subscriptions,
    patients, queue_entries, patient_followups, invoices, whatsapp_messages,
    partner_agreements, team_performance, statements, referral_followups,
    booking_settings, doctors, booking_counters, password_reset_requests,
)
from app.auth import hash_password
from app.utils.ids import new_id
from app.routers.referrals import _notify_patient_whatsapp
from app.admin_bootstrap import sync_super_admin
from app.config import ADMIN_EMAIL

DEMO_PASSWORD = "Roskyro@123"

# Partner category taxonomy -- the exact, curated list of categories a
# healthcare business can list itself under to join the Networking Marketing
# referral network. Two-level: a handful of broad groups (used for grouped <optgroup>
# dropdowns and the public marketing pages), each with specific leaf
# categories a partner actually picks. This is the definitive, exhaustive
# list -- not a superset of every possible service type -- per the
# product decision behind Networking Marketing's "Verified Healthcare Service Partners"
# positioning.
CATEGORY_GROUPS = [
    ("specialist_referrals", "👨‍⚕️ Specialist Referrals", [
        ("cardiologist", "Cardiologist"),
        ("orthopedic", "Orthopedic"),
        ("gynecologist", "Gynecologist"),
        ("pediatrician", "Pediatrician"),
        ("neurologist", "Neurologist"),
        ("gastroenterologist", "Gastroenterologist"),
        ("ent_specialist", "ENT Specialist"),
        ("dermatologist", "Dermatologist"),
        ("urologist", "Urologist"),
        ("oncologist", "Oncologist"),
        ("psychiatrist", "Psychiatrist"),
        ("other_specialists", "Other Specialists"),
    ]),
    # Merged "Diagnostics" + "Imaging" into one "Diagnostics & Imaging"
    # group per the user's expanded category list -- old slugs
    # (blood_test_labs, pathology_labs, home_sample_collection,
    # xray_centers, usg_centers, ct_scan_centers, mri_centers) are kept
    # unchanged since seed data below already references them; new
    # categories from the expanded list are appended.
    #
    # Further expanded per the user's follow-up list: renamed pet_scan_centers
    # / pft_centers display names to match the user's exact wording ("PET-CT
    # Centers" / "Pulmonary Function Labs" -- slugs untouched since seed data
    # already references them), and added 8 new leaf categories (mammography,
    # DEXA, cardiology/neurology diagnostic centers, histopathology, genetic
    # testing, molecular diagnostics, microbiology) that weren't covered yet.
    ("diagnostics_imaging", "🧪 Diagnostics & Imaging", [
        ("blood_test_labs", "Blood Test Labs"),
        ("pathology_labs", "Pathology Labs"),
        ("diagnostic_centers", "Diagnostic Centers"),
        ("home_sample_collection", "Home Sample Collection"),
        ("xray_centers", "X-Ray Centers"),
        ("usg_centers", "Ultrasound / Sonography Centers"),
        ("ct_scan_centers", "CT Scan Centers"),
        ("mri_centers", "MRI Scan Centers"),
        ("pet_scan_centers", "PET-CT Centers"),
        ("mammography_centers", "Mammography Centers"),
        ("dexa_scan_centers", "DEXA Scan Centers"),
        ("cardiology_diagnostic_centers", "Cardiology Diagnostic Centers"),
        ("neurology_diagnostic_centers", "Neurology Diagnostic Centers"),
        ("ecg_centers", "ECG Centers"),
        ("eeg_centers", "EEG Centers"),
        ("emg_ncv_centers", "EMG / NCV Centers"),
        ("pft_centers", "Pulmonary Function Labs"),
        ("sleep_study_labs", "Sleep Study Labs"),
        ("histopathology_labs", "Histopathology Labs"),
        ("genetic_testing_labs", "Genetic Testing Labs"),
        ("molecular_diagnostic_labs", "Molecular Diagnostic Labs"),
        ("microbiology_labs", "Microbiology Labs"),
    ]),
    # Renamed "Rehabilitation" -> "Rehabilitation & Therapy" and expanded
    # with the additional therapy categories from the user's list.
    ("rehabilitation_therapy", "🏃 Rehabilitation & Therapy", [
        ("physiotherapy_centers", "Physiotherapy Centers"),
        ("rehabilitation_centers", "Rehabilitation Centers"),
        ("occupational_therapy_centers", "Occupational Therapy Centers"),
        ("speech_therapy_centers", "Speech Therapy Centers"),
        ("pain_management_clinics", "Pain Management Clinics"),
        ("sports_injury_clinics", "Sports Injury Clinics"),
    ]),
    ("home_healthcare", "🏠 Home Healthcare", [
        ("physiotherapy_at_home", "Physiotherapy at Home"),
        ("elder_care_services", "Elder Care Services"),
    ]),
]

ROSKYRO_TEAM = [
    ("Aditi Rao", "admin@roskyro.com", "roskyro_admin"),
    ("Karan Mehta", "ops@roskyro.com", "roskyro_ops_manager"),
    ("Simran Kaur", "growth@roskyro.com", "roskyro_growth_expert"),
    ("Rohan Iyer", "content@roskyro.com", "roskyro_content_specialist"),
    ("Neha Sharma", "seo@roskyro.com", "roskyro_seo_specialist"),
    ("Farhan Sheikh", "gbp@roskyro.com", "roskyro_gbp_specialist"),
    ("Priya Nair", "reviews@roskyro.com", "roskyro_review_manager"),
    ("Vikram Joshi", "crm@roskyro.com", "roskyro_crm_executive"),
    ("Ayesha Khan", "support@roskyro.com", "roskyro_support_executive"),
    ("Manoj Pillai", "qa@roskyro.com", "roskyro_quality_reviewer"),
]


def now():
    return datetime.now(timezone.utc)


async def run():
    print("Clearing existing data...")
    for col in (
        audit_logs, reports, team_performance, tasks, notifications, approvals,
        visibility_score_history, marketing_performance, reviews, appointments,
        statements, settlements, settlement_rules,
        referral_followups, referral_status_history, referrals,
        partner_agreements, partner_services, partners, partner_categories,
        whatsapp_messages, invoices, patient_followups, queue_entries, patients,
        booking_settings, doctors, booking_counters,
        organization_subscriptions, plans_collection,
        users, organizations, password_reset_requests,
    ):
        await col.delete_many({})

    print("Seeding pricing plans...")
    plan_docs = [
        {
            "_id": "grow", "name": "GROW", "tagline": "Get More Patients through AI Visibility, Google Growth & Digital Marketing.",
            "monthly_price": 14999, "yearly_price": 143990, "badge": None,
            "description": "AI + human patient growth engine — visibility, reviews, SEO and content, all managed for you.",
            "best_for": "Doctors, Clinics, Diagnostic Labs, Hospitals",
            "customer_promise": "Hum marketing nahi, patient growth par kaam karte hain.",
            "is_bundle": False, "bundle_pillars": None,
            "features": ["AI Visibility Management", "Google Business Profile", "Review Growth", "Local SEO", "AI Search Optimization", "Social Media Management", "Content Creation", "Digital Marketing", "Monthly Growth Reports"],
            "sort_order": 1,
        },
        {
            "_id": "manage", "name": "MANAGE", "tagline": "Run your healthcare business efficiently with CRM, Appointments & Automation.",
            "monthly_price": 9999, "yearly_price": 95990, "badge": None,
            "description": "Day-to-day operations — CRM, appointments, queue, billing and communication in one place.",
            "best_for": "Clinics & Hospitals with growing patient volume",
            "customer_promise": "Hum aapke operations ko simple aur organized banate hain.",
            "is_bundle": False, "bundle_pillars": None,
            "features": ["Patient CRM", "Appointment Management", "Queue Management", "Follow-ups", "Billing", "WhatsApp Communication", "Reports", "AI + Human Support"],
            "sort_order": 2,
        },
        {
            "_id": "connect", "name": "Networking Marketing", "tagline": "Join India's trusted healthcare business network.",
            "monthly_price": 4999, "yearly_price": 47990, "badge": None,
            "description": "The ROSKYRO Healthcare Referral & Partner Network — trusted partners, tracked referrals, configurable settlements.",
            "best_for": "Clinics, Hospitals, Labs & Healthcare Businesses",
            "customer_promise": "Hum aapko trusted healthcare partners se jodte hain.",
            "is_bundle": False, "bundle_pillars": None,
            "features": ["Partner Directory", "Partner Network", "Service Requests", "Business Collaborations", "Analytics", "Digital Documents", "Opportunity Tracking"],
            "sort_order": 3,
        },
        {
            "_id": "complete", "name": "ROSKYRO Complete", "tagline": "Everything in Grow + Manage + Networking Marketing",
            "monthly_price": 24999, "yearly_price": 239990, "badge": "Most Popular",
            "description": "Everything ROSKYRO offers, at a bundled price — one team, one dashboard, one bill.",
            "best_for": "Multi-speciality Clinics, Hospitals & Healthcare Groups",
            "customer_promise": "Aapka poora digital business team, ek jagah.",
            "is_bundle": True, "bundle_pillars": ["grow", "manage", "connect"],
            "features": ["Dedicated Success Manager", "Priority Support", "Monthly Strategy Review", "Complete Healthcare Growth Platform"],
            "sort_order": 4,
        },
    ]
    await plans_collection.insert_many(plan_docs)
    monthly_price_by_code = {p["_id"]: p["monthly_price"] for p in plan_docs}

    print("Seeding partner categories...")
    cat_ids = {}
    sort_i = 0
    for group_slug, group_name, subcats in CATEGORY_GROUPS:
        for slug, name in subcats:
            cat_id = new_id()
            await partner_categories.insert_one({
                "_id": cat_id, "slug": slug, "name": name,
                "group_slug": group_slug, "group_name": group_name,
                "sort_order": sort_i, "is_active": True,
            })
            cat_ids[slug] = cat_id
            sort_i += 1

    password_hash = hash_password(DEMO_PASSWORD)

    # Every login-capable account (super admin, internal staff, a
    # customer's owner/doctor, a partner admin) needs its own mobile
    # number now -- login accepts mobile number + password, not just
    # email + password. Sequential/deterministic (not random) so the demo
    # numbers are stable and easy to document/hand to a tester.
    mobile_seq = itertools.count(9800000001)

    def next_mobile():
        return f"+91-{next(mobile_seq)}"

    print("Seeding ROSKYRO internal team...")
    team_ids = {}
    for name, email, role in ROSKYRO_TEAM:
        uid = new_id()
        await users.insert_one({
            "_id": uid, "org_id": None, "name": name, "email": email, "password_hash": password_hash,
            "phone": next_mobile(), "role": role, "status": "active", "avatar_url": None, "last_login_at": None,
            "created_at": now(), "updated_at": now(),
        })
        team_ids[role] = uid

    # -----------------------------------------------------------------
    # Customer organizations (healthcare businesses using ROSKYRO)
    # -----------------------------------------------------------------
    print("Seeding customer organizations + users...")

    async def make_org(name, business_type, city, state, is_partner):
        org_id = new_id()
        doc = {
            "_id": org_id, "name": name, "business_type": business_type, "city": city, "state": state,
            "phone": f"+91-98{random.randint(10000000, 99999999)}",
            "email": "".join(c if c.isalnum() else "." for c in name.lower()).strip(".") + "@example.com",
            "subscription_plan": random.choice(["starter", "growth", "scale"]),
            "status": "active", "is_partner": is_partner, "visibility_score": 55 + random.randint(0, 39),
            "legal_name": None, "address": None, "pincode": None, "website": None, "logo_url": None,
            "created_at": now(), "updated_at": now(),
        }
        await organizations.insert_one(doc)
        return doc

    sunrise_clinic = await make_org("Sunrise Family Clinic", "clinic", "Pune", "Maharashtra", False)
    smile_dental = await make_org("Smile Bright Dental", "dental", "Pune", "Maharashtra", False)
    vital_skin = await make_org("Vital Skin & Aesthetics", "skin_clinic", "Mumbai", "Maharashtra", False)
    active_life_physio = await make_org("ActiveLife Physiotherapy", "physiotherapy", "Bengaluru", "Karnataka", True)

    org_owners = {}
    for org, doctor_name in [
        (sunrise_clinic, "Dr. Anjali Deshmukh"), (smile_dental, "Dr. Rakesh Verma"),
        (vital_skin, "Dr. Meera Kapoor"), (active_life_physio, "Dr. Sameer Joshi"),
    ]:
        owner_id = new_id()
        await users.insert_one({
            "_id": owner_id, "org_id": org["_id"], "name": doctor_name, "email": org["email"],
            "password_hash": password_hash, "phone": next_mobile(), "role": "owner", "status": "active",
            "avatar_url": None, "last_login_at": None, "created_at": now(), "updated_at": now(),
        })
        doctor_id = new_id()
        await users.insert_one({
            "_id": doctor_id, "org_id": org["_id"], "name": f"{doctor_name} (Referring)", "email": f"doctor.{org['email']}",
            "password_hash": password_hash, "phone": next_mobile(), "role": "doctor", "status": "active",
            "avatar_url": None, "last_login_at": None, "created_at": now(), "updated_at": now(),
        })
        org_owners[org["_id"]] = {"ownerId": owner_id, "doctorId": doctor_id, "org": org}

    # Give demo orgs different pillar combinations so plan-gating is
    # actually visible when clicking around: full bundle, two pillars,
    # one pillar, and connect-only.
    print("Seeding pillar subscriptions...")
    subs = [
        (sunrise_clinic, ["complete"]),
        (smile_dental, ["grow", "connect"]),
        (vital_skin, ["manage"]),
        (active_life_physio, ["connect"]),
    ]
    for org, plan_codes in subs:
        for code in plan_codes:
            await organization_subscriptions.insert_one({
                "_id": new_id(), "org_id": org["_id"], "plan_code": code, "status": "active",
                "source": "signup", "activated_by": org_owners[org["_id"]]["ownerId"], "billing_cycle": "monthly",
                "price_at_purchase": monthly_price_by_code[code], "started_at": now(), "cancelled_at": None,
            })

    # -----------------------------------------------------------------
    # Partner organizations (service providers in the referral network)
    # -----------------------------------------------------------------
    print("Seeding partner organizations + partner profiles...")

    async def make_partner(name, business_type, city, category, verified, preferred, turnaround, services):
        org = await make_org(name, business_type, city, "Maharashtra", True)
        partner_admin_id = new_id()
        await users.insert_one({
            "_id": partner_admin_id, "org_id": org["_id"], "name": f"{name} Admin", "email": f"admin.{org['email']}",
            "password_hash": password_hash, "phone": next_mobile(), "role": "partner_admin", "status": "active",
            "avatar_url": None, "last_login_at": None, "created_at": now(), "updated_at": now(),
        })
        partner_id = new_id()
        partner_doc = {
            "_id": partner_id, "org_id": org["_id"], "category_id": cat_ids[category],
            "verification_status": "verified" if verified else "pending",
            "verified_by": team_ids["roskyro_ops_manager"] if verified else None,
            "verified_at": now() if verified else None,
            "coverage_area": f"{city} and surrounding areas", "coverage_cities": [city], "turnaround_time": turnaround,
            "contact_person": f"{name} Front Desk", "contact_phone": org["phone"], "contact_email": org["email"],
            "rating_avg": round(3.8 + random.random() * 1.2, 2) if verified else 0,
            "rating_count": random.randint(20, 169) if verified else 0,
            "preferred_partner": bool(preferred), "is_available_now": random.random() > 0.3,
            "total_referrals_received": random.randint(0, 39), "total_referrals_completed": random.randint(0, 34),
            "avg_report_time_hours": round(6 + random.random() * 30, 1) if verified else None,
            "payout_upi_id": None, "payout_note": None, "working_hours": None,
            "created_at": now(), "updated_at": now(),
        }
        await partners.insert_one(partner_doc)
        for s in services:
            await partner_services.insert_one({
                "_id": new_id(), "partner_id": partner_id, "name": s["name"], "description": s.get("description"),
                "price": s["price"], "price_unit": s.get("unit", "per service"), "turnaround_time": s.get("turnaround", turnaround),
                "is_active": True, "created_at": now(),
            })
        return {"org": org, "partner": partner_doc, "partnerAdminId": partner_admin_id}

    cityscan_diagnostics = await make_partner(
        "CityScan Diagnostics", "diagnostic_lab", "Pune", "pathology_labs", True, True, "Same day",
        [{"name": "Complete Blood Count (CBC)", "description": "Full blood panel", "price": 400},
         {"name": "Lipid Profile", "description": "Cholesterol panel", "price": 650},
         {"name": "Thyroid Panel (T3/T4/TSH)", "description": "", "price": 800}],
    )
    punelife_mri = await make_partner(
        "PuneLife Imaging Centre", "imaging_centre", "Pune", "mri_centers", True, False, "24-48 hrs",
        [{"name": "MRI Brain", "description": "With contrast option", "price": 6500},
         {"name": "CT Scan Abdomen", "description": "", "price": 4500},
         {"name": "Ultrasound (Sonography)", "description": "", "price": 1200}],
    )
    clear_vision_eye = await make_partner(
        # No dedicated ophthalmology category in the curated Networking Marketing
        # taxonomy -- "Other Specialists" is the closest fit.
        "ClearVision Eye Hospital", "eye_hospital", "Mumbai", "other_specialists", True, True, "Same day consult",
        [{"name": "Comprehensive Eye Checkup", "description": "", "price": 500},
         {"name": "Cataract Surgery Consult", "description": "", "price": 1000}],
    )
    homecare_plus = await make_partner(
        "HomeCare Plus", "home_healthcare", "Pune", "physiotherapy_at_home", False, False, "2-4 hrs response",
        [{"name": "At-home Nursing Visit", "description": "", "price": 900, "unit": "per visit"},
         {"name": "Physiotherapy at Home", "description": "", "price": 700, "unit": "per session"}],
    )
    pune_heart_care = await make_partner(
        # Replaces the old "Metro Ambulance Services" demo partner --
        # ambulance/transport isn't part of the curated Networking Marketing category
        # list, so this slot became a cardiology specialist instead
        # (keeps the same emergency/in-progress referral scenario below).
        "Pune Heart Care Centre", "specialist_clinic", "Pune", "cardiologist", True, False, "Same day",
        [{"name": "Emergency Cardiology Consult", "description": "", "price": 1500},
         {"name": "ECG & Stress Test", "description": "", "price": 1200}],
    )

    # ActiveLife Physio is itself both a customer and a network partner (physio category)
    active_life_partner_id = new_id()
    active_life_partner_doc = {
        "_id": active_life_partner_id, "org_id": active_life_physio["_id"], "category_id": cat_ids["physiotherapy_centers"],
        "verification_status": "verified", "verified_by": team_ids["roskyro_ops_manager"], "verified_at": now(),
        "coverage_area": "Bengaluru and surrounding areas", "coverage_cities": ["Bengaluru"], "turnaround_time": "24 hrs",
        "contact_person": "ActiveLife Front Desk", "contact_phone": active_life_physio["phone"], "contact_email": active_life_physio["email"],
        "rating_avg": 4.5, "rating_count": 60, "preferred_partner": True, "is_available_now": True,
        "total_referrals_received": 18, "total_referrals_completed": 15, "avg_report_time_hours": 10,
        "payout_upi_id": None, "payout_note": None, "working_hours": None, "created_at": now(), "updated_at": now(),
    }
    await partners.insert_one(active_life_partner_doc)
    await partner_services.insert_one({
        "_id": new_id(), "partner_id": active_life_partner_id, "name": "Post-Surgery Rehab Program",
        "description": "Comprehensive rehab", "price": 4500, "price_unit": "per program",
        "turnaround_time": "24 hrs", "is_active": True, "created_at": now(),
    })

    # -----------------------------------------------------------------
    # Referral Bonus rules — deliberately mixed: some 'none', some flat rupee
    # amounts. Percentage-based settlement has been removed entirely.
    # -----------------------------------------------------------------
    print("Seeding settlement rules...")
    platform_rule = {"_id": new_id(), "scope": "platform", "org_id": None, "partner_id": None, "category_id": None,
                      "settlement_type": "none", "flat_fee_amount": None, "percentage_rate": None, "custom_terms": None,
                      "is_active": True, "created_by": team_ids["roskyro_admin"], "created_at": now()}
    await settlement_rules.insert_one(platform_rule)
    cityscan_rule = {"_id": new_id(), "scope": "partner", "org_id": None, "partner_id": cityscan_diagnostics["partner"]["_id"],
                      "category_id": None, "settlement_type": "flat_fee", "flat_fee_amount": 150, "percentage_rate": None,
                      "custom_terms": None, "is_active": True, "created_by": team_ids["roskyro_admin"], "created_at": now()}
    await settlement_rules.insert_one(cityscan_rule)
    punelife_rule = {"_id": new_id(), "scope": "partner", "org_id": None, "partner_id": punelife_mri["partner"]["_id"],
                      "category_id": None, "settlement_type": "flat_fee", "flat_fee_amount": 300, "percentage_rate": None,
                      "custom_terms": None, "is_active": True, "created_by": team_ids["roskyro_admin"], "created_at": now()}
    await settlement_rules.insert_one(punelife_rule)

    # Category-level default Marketing Fees -- sit between a business-
    # specific "org" override and the platform-wide fallback in the
    # resolution order (see routers/referrals.py). Without these, every
    # partner that hasn't self-set their own rate (or been given a
    # negotiated override) falls all the way through to the single
    # platform-wide number above -- which doesn't account for a ~₹200
    # blood test and a ~₹8,000 MRI scan being worth very different flat
    # fees. Amounts below are illustrative defaults, roughly scaled to
    # each category's typical real-world service price; ROSKYRO can tune
    # them anytime via /settlements/category-rates (see the "Fee Rules"
    # section of Pricing & Payments in the internal dashboard). Only a
    # representative set is seeded here -- not every category needs a
    # default from day one, and any category left unset simply falls
    # through to the platform default, same as before this feature existed.
    CATEGORY_DEFAULT_FEES = {
        "blood_test_labs": 40, "pathology_labs": 50, "diagnostic_centers": 100,
        "home_sample_collection": 30, "xray_centers": 60, "usg_centers": 120,
        "ct_scan_centers": 350, "mri_centers": 500, "pet_scan_centers": 700,
        "mammography_centers": 150, "dexa_scan_centers": 150,
        "cardiology_diagnostic_centers": 200, "neurology_diagnostic_centers": 200,
        "ecg_centers": 50, "eeg_centers": 150, "emg_ncv_centers": 200,
        "pft_centers": 100, "sleep_study_labs": 300, "histopathology_labs": 150,
        "genetic_testing_labs": 600, "molecular_diagnostic_labs": 500,
        "microbiology_labs": 80,
        "physiotherapy_centers": 150, "rehabilitation_centers": 200,
        "occupational_therapy_centers": 150, "speech_therapy_centers": 150,
        "pain_management_clinics": 200, "sports_injury_clinics": 200,
        "physiotherapy_at_home": 150, "elder_care_services": 200,
    }
    for slug, amount in CATEGORY_DEFAULT_FEES.items():
        await settlement_rules.insert_one({
            "_id": new_id(), "scope": "category", "org_id": None, "partner_id": None, "category_id": cat_ids[slug],
            "settlement_type": "flat_fee", "flat_fee_amount": amount, "percentage_rate": None,
            "custom_terms": None, "is_active": True, "created_by": team_ids["roskyro_admin"], "created_at": now(),
        })

    # -----------------------------------------------------------------
    # Referrals across the full status range
    # -----------------------------------------------------------------
    print("Seeding referrals...")
    referral_specs = [
        {"from": sunrise_clinic, "partner": cityscan_diagnostics, "patient": "Ramesh Pawar", "service": "Complete Blood Count (CBC)", "status": "completed"},
        {"from": sunrise_clinic, "partner": punelife_mri, "patient": "Sunita Joshi", "service": "MRI Brain", "status": "report_uploaded"},
        {"from": sunrise_clinic, "partner": pune_heart_care, "patient": "Ganesh Kale", "service": "Emergency Cardiology Consult", "status": "in_progress", "urgency": "emergency"},
        {"from": sunrise_clinic, "partner": homecare_plus, "patient": "Lata Bhosale", "service": "At-home Nursing Visit", "status": "pending_review"},
        {"from": smile_dental, "partner": clear_vision_eye, "patient": "Amit Kulkarni", "service": "Comprehensive Eye Checkup", "status": "sent"},
        {"from": smile_dental, "partner": cityscan_diagnostics, "patient": "Priyanka Shah", "service": "Thyroid Panel (T3/T4/TSH)", "status": "accepted"},
        {"from": vital_skin, "partner": punelife_mri, "patient": "Rahul Menon", "service": "Ultrasound (Sonography)", "status": "declined"},
        {"from": vital_skin, "partner": cityscan_diagnostics, "patient": "Kavita Iyer", "service": "Lipid Profile", "status": "completed"},
    ]

    ref_counter = 1
    for spec in referral_specs:
        code = f"RSK-REF-{str(ref_counter).zfill(6)}"
        ref_counter += 1
        owner_id = org_owners[spec["from"]["_id"]]["ownerId"]
        doctor_id = org_owners[spec["from"]["_id"]]["doctorId"]
        requires_review = spec["partner"]["partner"]["verification_status"] != "verified"
        status = spec["status"]

        sent_at = now() - timedelta(days=3) if status in ("sent", "accepted", "in_progress", "report_uploaded", "completed", "declined") else None
        accepted_at = now() - timedelta(days=2) if status in ("accepted", "in_progress", "report_uploaded", "completed") else None
        completed_at = now() - timedelta(days=1) if status == "completed" else None

        referral_id = new_id()
        referral_doc = {
            "_id": referral_id, "referral_code": code, "referring_org_id": spec["from"]["_id"],
            "referring_user_id": doctor_id, "partner_id": spec["partner"]["partner"]["_id"],
            "category_id": spec["partner"]["partner"]["category_id"], "patient_name": spec["patient"],
            "patient_phone": f"+91-90{random.randint(10000000, 99999999)}", "patient_age": 20 + random.randint(0, 54),
            "patient_gender": random.choice(["Male", "Female"]), "service_requested": spec["service"],
            "clinical_notes": None, "urgency": spec.get("urgency", "routine"), "status": status,
            "ai_partner_suggested": False, "requires_roskyro_review": requires_review,
            "sent_at": sent_at, "accepted_at": accepted_at, "declined_at": now() - timedelta(days=2) if status == "declined" else None,
            "completed_at": completed_at, "cancelled_at": None, "decline_reason": None,
            "created_at": now() - timedelta(days=4), "updated_at": now(),
        }
        await referrals.insert_one(referral_doc)

        # Build the exact history trail up to (and including) the seeded
        # current status, following the real state machine -- 'declined'
        # branches off right after 'sent' instead of continuing the happy path.
        happy_path = (
            ["draft", "pending_review", "sent", "accepted", "in_progress", "report_uploaded", "completed"]
            if requires_review else
            ["draft", "sent", "accepted", "in_progress", "report_uploaded", "completed"]
        )
        if status == "declined":
            sent_idx = happy_path.index("sent")
            history_steps = happy_path[: sent_idx + 1] + ["declined"]
        else:
            idx = happy_path.index(status)
            history_steps = happy_path[: idx + 1]
        for step in history_steps:
            await referral_status_history.insert_one({
                "_id": new_id(), "referral_id": referral_id, "status": step, "changed_by": doctor_id,
                "note": f"Auto-seeded: {step}", "changed_at": now(),
            })

        # Seed the same patient WhatsApp notifications the live
        # create_referral/transition_referral endpoints send at each
        # lifecycle event -- driven off history_steps so a seeded
        # "declined" referral still shows the patient was told where they
        # were referred (sent happened before it got declined), just like
        # in real usage.
        for event in ("sent", "accepted", "report_uploaded", "completed"):
            if event in history_steps:
                await _notify_patient_whatsapp(referral_doc, event)

        if status == "completed":
            partner_id = spec["partner"]["partner"]["_id"]
            # Mirrors routers/referrals.py's real resolution order (minus
            # org_partner_pair and business-specific "org" overrides, which
            # this demo data doesn't seed): partner's own rate -> category
            # default -> platform fallback.
            rule = await settlement_rules.find_one({"scope": "partner", "partner_id": partner_id, "is_active": True})
            if not rule:
                rule = await settlement_rules.find_one({"scope": "category", "category_id": referral_doc["category_id"], "is_active": True})
            if not rule:
                rule = await settlement_rules.find_one({"scope": "platform", "is_active": True})
            if rule and rule["settlement_type"] != "none":
                # Marketing Fee: a flat rupee amount only -- percentage-
                # based settlement has been removed entirely. Owed by the
                # PARTNER to ROSKYRO (patient referral = marketing the
                # referring business did for the partner).
                amount = float(rule["flat_fee_amount"]) if rule["settlement_type"] == "flat_fee" else 0
                # Demo the two-sided confirmation states: Kavita Iyer's
                # settlement is seeded with the partner (CityScan
                # Diagnostics) already having clicked "I've Paid ROSKYRO,"
                # so ROSKYRO internal has a live "Confirm Received" action
                # to click in the demo -- every other seeded settlement is
                # untouched (fully pending, neither side has acted).
                payer_claimed = spec["patient"] == "Kavita Iyer"
                await settlements.insert_one({
                    "_id": new_id(), "referral_id": referral_id, "rule_id": rule["_id"], "org_id": spec["from"]["_id"],
                    "partner_id": partner_id, "settlement_type": rule["settlement_type"], "amount": amount,
                    "status": "pending", "paid_at": None,
                    "payer_marked_paid_at": (now() - timedelta(hours=6)) if payer_claimed else None,
                    "payment_reference": "UPI-DEMO-REF-88213" if payer_claimed else None,
                    "confirmed_by": None, "included_in_payout_id": None,
                    "period_month": now().strftime("%Y-%m"), "created_at": now(),
                })

    # -----------------------------------------------------------------
    # Appointments, reviews, marketing, visibility, approvals
    # -----------------------------------------------------------------
    print("Seeding appointments, reviews, marketing performance...")
    this_month = now().strftime("%Y-%m")
    for org in (sunrise_clinic, smile_dental, vital_skin):
        for i in range(8):
            days_ago = random.randint(0, 19)
            appt_date = (now() - timedelta(days=days_ago)).date().isoformat()
            await appointments.insert_one({
                "_id": new_id(), "org_id": org["_id"], "patient_name": f"Patient {i + 1}", "patient_phone": None,
                "doctor_name": "Dr. On Duty", "appointment_date": appt_date, "appointment_time": f"{9 + (i % 8)}:00",
                "status": "scheduled" if days_ago == 0 else "completed",
                "source": ["walk_in", "google", "website", "referral"][i % 4],
                "is_new_patient": random.random() > 0.6, "revenue_amount": 500 + random.randint(0, 2999),
                "booked_via": None, "token_number": None, "payment_status": "not_required",
                "payment_amount": None, "patient_note": None, "created_at": now(),
            })

        await reviews.insert_one({
            "_id": new_id(), "org_id": org["_id"], "platform": "google", "patient_name": "Happy Patient",
            "rating": 5, "comment": "Excellent care and very professional staff!", "status": "published",
            "ai_reply_draft": None, "human_reply": None, "replied_by": None, "created_at": now(),
        })
        await reviews.insert_one({
            "_id": new_id(), "org_id": org["_id"], "platform": "google", "patient_name": "Concerned Patient",
            "rating": 3, "comment": "Waiting time was longer than expected.", "status": "pending_response",
            "ai_reply_draft": "Thank you for the feedback — we are working on reducing wait times and would love the chance to make your next visit better.",
            "human_reply": None, "replied_by": None, "created_at": now(),
        })
        for channel in ("google_business", "seo", "social"):
            await marketing_performance.insert_one({
                "_id": new_id(), "org_id": org["_id"], "period_month": this_month, "channel": channel,
                "impressions": 1000 + random.randint(0, 3999), "clicks": 50 + random.randint(0, 299),
                "leads": 5 + random.randint(0, 39), "conversions": 1 + random.randint(0, 9), "created_at": now(),
            })
        await visibility_score_history.insert_one({
            "_id": new_id(), "org_id": org["_id"], "period_month": this_month, "score": 60 + random.randint(0, 34),
            "breakdown": {"gbp_completeness": 80, "review_velocity": 65, "seo_health": 70}, "created_at": now(),
        })
        await approvals.insert_one({
            "_id": new_id(), "org_id": org["_id"], "approval_type": "social_post", "title": "Instagram post: World Health Day",
            "description": "AI-drafted caption + graphic, reviewed by Content Specialist, awaiting your go-ahead before it is published.",
            "ai_generated": True, "prepared_by": team_ids["roskyro_content_specialist"], "status": "pending",
            "decided_by": None, "decided_at": None, "created_at": now(),
        })
        await reports.insert_one({
            "_id": new_id(), "org_id": org["_id"], "report_type": "monthly_growth", "period_month": this_month,
            "summary": {"newPatients": 12, "revenueGrowthPct": 8.4, "reviewsGained": 5, "referralsSent": 2},
            "file_url": None, "generated_by": team_ids["roskyro_growth_expert"], "created_at": now(),
        })

    # -----------------------------------------------------------------
    # MANAGE pillar data: Patient CRM, Queue, Follow-ups, Billing,
    # WhatsApp -- seeded for orgs that actually hold the MANAGE pillar
    # (Sunrise via the Complete bundle, Vital Skin standalone).
    # -----------------------------------------------------------------
    print("Seeding MANAGE pillar data (CRM, queue, follow-ups, billing, WhatsApp)...")
    manage_patient_names = ["Ramesh Pawar", "Sunita Joshi", "Amit Kulkarni", "Priyanka Shah", "Kavita Iyer", "Rahul Menon"]
    for org in (sunrise_clinic, vital_skin):
        for name in manage_patient_names:
            await patients.insert_one({
                "_id": new_id(), "org_id": org["_id"], "name": name,
                "phone": f"+91-9{random.randint(100000000, 999999999)}", "email": None,
                "age": 22 + random.randint(0, 49), "gender": random.choice(["Male", "Female"]),
                "tags": ["vip"] if random.random() > 0.7 else ["regular"], "notes": None,
                "last_visit_at": (now() - timedelta(days=random.randint(0, 30))).date().isoformat(),
                "total_visits": 2 + random.randint(0, 7), "lifetime_value": 2000 + random.randint(0, 14999),
                "created_at": now(), "updated_at": now(),
            })

        # Today's live queue
        base = now()
        for i, status in enumerate(["waiting", "waiting", "in_consultation", "done"]):
            checked_in_at = base - timedelta(minutes=(4 - i) * 12)
            called_at = checked_in_at + timedelta(minutes=5) if status in ("in_consultation", "done") else None
            completed_at = checked_in_at + timedelta(minutes=15) if status == "done" else None
            await queue_entries.insert_one({
                "_id": new_id(), "org_id": org["_id"], "appointment_id": None, "patient_name": manage_patient_names[i],
                "token_number": i + 1, "doctor_name": "Dr. On Duty", "status": status,
                "checked_in_at": checked_in_at, "called_at": called_at, "completed_at": completed_at,
            })

        # Pending follow-ups
        await patient_followups.insert_one({
            "_id": new_id(), "org_id": org["_id"], "patient_name": manage_patient_names[0], "patient_phone": "+91-9800000001",
            "reason": "Post-treatment check-in", "due_date": now().date().isoformat(), "status": "pending",
            "notes": None, "completed_at": None, "created_by": org_owners[org["_id"]]["doctorId"], "created_at": now(),
        })
        await patient_followups.insert_one({
            "_id": new_id(), "org_id": org["_id"], "patient_name": manage_patient_names[1], "patient_phone": "+91-9800000002",
            "reason": "Lab result review", "due_date": (now() + timedelta(days=2)).date().isoformat(), "status": "pending",
            "notes": None, "completed_at": None, "created_by": org_owners[org["_id"]]["doctorId"], "created_at": now(),
        })
        await patient_followups.insert_one({
            "_id": new_id(), "org_id": org["_id"], "patient_name": manage_patient_names[2], "patient_phone": "+91-9800000003",
            "reason": "Routine check-up", "due_date": (now() - timedelta(days=3)).date().isoformat(), "status": "done",
            "notes": None, "completed_at": now() - timedelta(days=2), "created_by": org_owners[org["_id"]]["doctorId"], "created_at": now(),
        })

        # Invoices
        await invoices.insert_one({
            "_id": new_id(), "invoice_number": f"INV-{org['_id'][:6]}-01", "org_id": org["_id"],
            "patient_name": manage_patient_names[3], "patient_phone": "+91-9800000004", "appointment_id": None,
            "line_items": [{"description": "Consultation", "quantity": 1, "unitPrice": 500}, {"description": "Lab Test", "quantity": 1, "unitPrice": 1000}],
            "subtotal": 1500, "discount": 0, "tax": 75, "total": 1575, "status": "paid",
            "due_date": (now() - timedelta(days=5)).date().isoformat(), "paid_at": now(),
            "created_by": org_owners[org["_id"]]["doctorId"], "created_at": now(),
        })
        await invoices.insert_one({
            "_id": new_id(), "invoice_number": f"INV-{org['_id'][:6]}-02", "org_id": org["_id"],
            "patient_name": manage_patient_names[4], "patient_phone": "+91-9800000005", "appointment_id": None,
            "line_items": [{"description": "Procedure", "quantity": 1, "unitPrice": 2200}],
            "subtotal": 2200, "discount": 0, "tax": 110, "total": 2310, "status": "sent",
            "due_date": (now() + timedelta(days=7)).date().isoformat(), "paid_at": None,
            "created_by": org_owners[org["_id"]]["doctorId"], "created_at": now(),
        })

        # WhatsApp communication log
        msg0 = f"Hi {manage_patient_names[0]}, this is a reminder for your upcoming appointment. Reply CONFIRM to confirm or CALL if you need to reschedule."
        await whatsapp_messages.insert_one({
            "_id": new_id(), "org_id": org["_id"], "patient_name": manage_patient_names[0], "patient_phone": "+91-9800000001",
            "direction": "outbound", "template_name": "appointment_reminder", "message": msg0, "status": "delivered",
            "sent_by": org_owners[org["_id"]]["ownerId"], "created_at": now(),
        })
        msg3 = f"Thank you for visiting us, {manage_patient_names[3]}! We'd really appreciate a quick Google review — it helps other patients find quality care."
        await whatsapp_messages.insert_one({
            "_id": new_id(), "org_id": org["_id"], "patient_name": manage_patient_names[3], "patient_phone": "+91-9800000004",
            "direction": "outbound", "template_name": "review_request", "message": msg3, "status": "read",
            "sent_by": org_owners[org["_id"]]["ownerId"], "created_at": now(),
        })

    # -----------------------------------------------------------------
    # QR self-booking: org-wide settings (UPI, booking window) + a
    # multi-doctor faculty roster per org, each on their own weekly
    # schedule/fee -- this is what makes the demo actually show off
    # multispeciality booking (different faculty, different days/times/
    # fees) rather than one flat clinic-wide slot grid.
    # -----------------------------------------------------------------
    print("Seeding QR self-booking settings + doctor/faculty rosters...")

    async def make_doctor(org, name, specialty, fee, schedule, slot_minutes=30, capacity=1):
        doc = {
            "_id": new_id(), "org_id": org["_id"], "name": name, "specialty": specialty,
            "consultation_fee": fee, "slot_duration_minutes": slot_minutes, "capacity_per_slot": capacity,
            "weekly_schedule": [{"day": d, "open_time": o, "close_time": c} for (d, o, c) in schedule],
            "is_active": True, "created_at": now(), "updated_at": now(),
        }
        await doctors.insert_one(doc)
        return doc

    async def enable_booking(org, upi_id, window_days=7):
        await booking_settings.insert_one({
            "_id": new_id(), "org_id": org["_id"], "is_enabled": True, "upi_id": upi_id,
            "booking_window_days": window_days, "updated_by": org_owners[org["_id"]]["ownerId"],
            "created_at": now(), "updated_at": now(),
        })

    # Sunrise Family Clinic -- a multispeciality-style general clinic with
    # three faculty on different days/times/fees.
    await enable_booking(sunrise_clinic, "sunrise.clinic@okhdfcbank")
    await make_doctor(
        sunrise_clinic, "Dr. Anjali Deshmukh", "General Physician", 300,
        [("mon", "10:00", "14:00"), ("tue", "10:00", "14:00"), ("wed", "10:00", "14:00"),
         ("thu", "10:00", "14:00"), ("fri", "10:00", "14:00")],
        slot_minutes=20,
    )
    await make_doctor(
        sunrise_clinic, "Dr. Sameer Kulkarni", "Pediatrician", 400,
        [("mon", "16:00", "19:00"), ("wed", "16:00", "19:00"), ("fri", "16:00", "19:00")],
        slot_minutes=20,
    )
    await make_doctor(
        sunrise_clinic, "Dr. Neha Joshi", "Dermatologist", 500,
        [("tue", "11:00", "13:00"), ("thu", "11:00", "13:00"), ("sat", "11:00", "14:00")],
        slot_minutes=30,
    )

    # Vital Skin & Aesthetics -- two faculty, skin-clinic specialties.
    await enable_booking(vital_skin, "vitalskin.clinic@okhdfcbank")
    await make_doctor(
        vital_skin, "Dr. Meera Kapoor", "Dermatologist", 600,
        [("mon", "10:00", "13:00"), ("tue", "10:00", "13:00"), ("wed", "10:00", "13:00"),
         ("thu", "10:00", "13:00"), ("fri", "10:00", "13:00"), ("sat", "10:00", "13:00")],
        slot_minutes=30,
    )
    await make_doctor(
        vital_skin, "Dr. Kabir Shah", "Cosmetologist", 800,
        [("tue", "14:00", "18:00"), ("thu", "14:00", "18:00"), ("sat", "14:00", "18:00")],
        slot_minutes=45, capacity=1,
    )

    # -----------------------------------------------------------------
    # Internal tasks (Team Dashboard queues)
    # -----------------------------------------------------------------
    print("Seeding internal tasks...")
    task_specs = [
        {"role": "roskyro_ops_manager", "type": "partner_verification", "title": "Verify HomeCare Plus partner application", "priority": "high", "hours": 24},
        {"role": "roskyro_content_specialist", "type": "content_creation", "title": "Draft Instagram post for Smile Bright Dental", "priority": "normal", "hours": 48},
        {"role": "roskyro_seo_specialist", "type": "seo_audit", "title": "Monthly SEO audit — Vital Skin & Aesthetics", "priority": "normal", "hours": 72},
        {"role": "roskyro_gbp_specialist", "type": "gbp_update", "title": "Update Google Business hours for Sunrise Clinic", "priority": "low", "hours": 24},
        {"role": "roskyro_review_manager", "type": "review_response", "title": "Respond to 3-star review — Sunrise Clinic", "priority": "high", "hours": 12},
        {"role": "roskyro_crm_executive", "type": "crm_followup", "title": "Follow up on referral RSK-REF-000004 (pending review)", "priority": "urgent", "hours": 4},
        {"role": "roskyro_support_executive", "type": "support_ticket", "title": "Sunrise Clinic — question about invoice", "priority": "normal", "hours": 24},
        {"role": "roskyro_quality_reviewer", "type": "quality_check", "title": "QA check: AI reply drafts before publishing", "priority": "normal", "hours": 24},
    ]
    task_ids_by_title = {}
    for t in task_specs:
        task_id = new_id()
        await tasks.insert_one({
            "_id": task_id, "org_id": None, "related_type": None, "related_id": None, "title": t["title"],
            "description": None, "task_type": t["type"], "assigned_role": t["role"], "assigned_to": None,
            "priority": t["priority"], "status": "open", "sla_hours": t["hours"],
            "sla_due_at": now() + timedelta(hours=t["hours"]), "created_by": None, "completed_at": None, "created_at": now(),
        })
        task_ids_by_title[t["title"]] = task_id

    # A couple already assigned + one overdue for demo realism
    await tasks.update_one(
        {"title": "Draft Instagram post for Smile Bright Dental"},
        {"$set": {"assigned_to": team_ids["roskyro_content_specialist"], "status": "in_progress"}},
    )
    await tasks.update_one(
        {"title": "Update Google Business hours for Sunrise Clinic"},
        {"$set": {"sla_due_at": now() - timedelta(hours=5), "priority": "urgent"}},
    )

    # Reconcile the super-admin account with ADMIN_EMAIL / ADMIN_PASSWORD
    # (see app/admin_bootstrap.py) -- if those env vars are set to a real
    # production login, re-running this seed must NOT quietly reset the
    # admin account back to admin@roskyro.com / Roskyro@123.
    await sync_super_admin()

    print("\nSeed complete.\n")
    print("Demo password for ALL OTHER seeded accounts:", DEMO_PASSWORD)
    print("\n--- Login as ---")
    print("ROSKYRO Admin (internal):        " + ADMIN_EMAIL + "  (password = ADMIN_PASSWORD env var, or Roskyro@123 if unset)")
    print("ROSKYRO Ops Manager (internal):  ops@roskyro.com")
    print("Clinic owner (customer):         " + sunrise_clinic["email"])
    print("Partner admin (partner):         admin." + cityscan_diagnostics["org"]["email"])


if __name__ == "__main__":
    asyncio.run(run())

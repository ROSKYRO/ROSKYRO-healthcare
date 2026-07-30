"""The registration-time "Business type" / "Business category" taxonomy for
a NEW business signing up via the public Register page (routers/auth.py's
`register()`).

Round 22 rewrite: business_type used to double as the business's medical
SPECIALTY (clinic/dental/skin_clinic/eye_hospital/etc) while business_category
was a separate, purely-informational size/scale picker (solo_doctor/clinic/
hospital). Product ask was to flip this: business_type is now the broad kind
of healthcare organization (Hospital, Clinic, Diagnostic Center, Pharmacy,
...), and business_category is a SPECIALTY dropdown that depends on whichever
business_type was picked (e.g. Hospital -> Cardiac Hospital / Trauma Center /
...; Clinic -> Cardiology / Dermatology / ...).

This module is the backend's single source of truth for that taxonomy.
frontend/src/lib/businessTaxonomy.js is a hand-kept mirror (same slugs/labels,
same structure) -- there's no shared build step between the two codebases, so
if this file's slugs change, that file needs the matching edit.

Deliberately NOT enforced as a strict (type, category) pair server-side: the
category value is only checked against the union of every type's valid
categories (ALL_VALID_BUSINESS_CATEGORIES below), not scoped to whichever
business_type was submitted alongside it. Two reasons: (1) the existing
business_category field was already independent/loosely-validated before this
round (see the retained LEGACY_BUSINESS_CATEGORIES below) and several existing
tests rely on that looseness (e.g. registering businessType="clinic" with
businessCategory="hospital"); (2) the frontend dropdown already only ever
offers the correct categories for the selected type, so a mismatched pair
reaching the API is not a real-world path, only a hypothetical direct-API
call -- not worth the risk of breaking existing behavior to close it.
"""

# (slug, label) pairs, in the order they should appear in the dropdown.
BUSINESS_TYPES = [
    ("hospital", "Hospital"),
    ("clinic", "Clinic"),
    ("diagnostic_center", "Diagnostic Center"),
    ("imaging_center", "Imaging Center"),
    ("pathology_lab", "Pathology Lab"),
    ("blood_collection_center", "Blood Collection Center"),
    ("pharmacy", "Pharmacy"),
    ("physiotherapy_rehab", "Physiotherapy & Rehabilitation Center"),
    ("home_healthcare_provider", "Home Healthcare Provider"),
    ("ambulance_service", "Ambulance Service"),
    ("blood_bank", "Blood Bank"),
    ("ivf_fertility_center", "IVF & Fertility Center"),
    ("dialysis_center", "Dialysis Center"),
    ("vaccination_center", "Vaccination Center"),
    ("wellness_center", "Wellness Center"),
    ("eye_care_center", "Eye Care Center"),
    ("dental_center", "Dental Center"),
    ("mental_health_center", "Mental Health Center"),
    ("medical_equipment_supplier", "Medical Equipment Supplier"),
    ("healthcare_service_provider", "Healthcare Service Provider"),
    ("other", "Other"),
]

# business_type slug -> list of (category slug, category label) valid for it.
# Hospital / Clinic / Diagnostic Center / Imaging Center / Physiotherapy &
# Rehabilitation Center have an explicit specialty breakdown (product-
# specified). Every other type has no requested breakdown yet, so its only
# category option is itself -- the dropdown still works (never empty/broken)
# without ROSKYRO inventing sub-specialties nobody asked for.
CATEGORIES_BY_TYPE = {
    "hospital": [
        ("multi_speciality_hospital", "Multi-Speciality Hospital"),
        ("super_speciality_hospital", "Super Speciality Hospital"),
        ("general_hospital", "General Hospital"),
        ("childrens_hospital", "Children's Hospital"),
        ("womens_hospital", "Women's Hospital"),
        ("cancer_hospital", "Cancer Hospital"),
        ("cardiac_hospital", "Cardiac Hospital"),
        ("orthopedic_hospital", "Orthopedic Hospital"),
        ("eye_hospital", "Eye Hospital"),
        ("ent_hospital", "ENT Hospital"),
        ("government_hospital", "Government Hospital"),
        ("medical_college_hospital", "Medical College Hospital"),
        ("trauma_center", "Trauma Center"),
    ],
    "clinic": [
        ("general_physician", "General Physician"),
        ("pediatrics", "Pediatrics"),
        ("gynecology_obstetrics", "Gynecology & Obstetrics"),
        ("orthopedics", "Orthopedics"),
        ("cardiology", "Cardiology"),
        ("neurology", "Neurology"),
        ("dermatology", "Dermatology"),
        ("psychiatry", "Psychiatry"),
        ("psychology", "Psychology"),
        ("gastroenterology", "Gastroenterology"),
        ("pulmonology", "Pulmonology"),
        ("endocrinology", "Endocrinology"),
        ("nephrology", "Nephrology"),
        ("urology", "Urology"),
        ("oncology", "Oncology"),
        ("rheumatology", "Rheumatology"),
        ("ent", "ENT"),
        ("ophthalmology", "Ophthalmology"),
        ("dental", "Dental"),
        ("physiotherapy", "Physiotherapy"),
        ("ayurveda", "Ayurveda"),
        ("homeopathy", "Homeopathy"),
        ("unani", "Unani"),
        ("siddha", "Siddha"),
        ("naturopathy", "Naturopathy"),
        ("cosmetic_aesthetic", "Cosmetic & Aesthetic"),
        ("pain_management", "Pain Management"),
        ("diabetology", "Diabetology"),
        ("other", "Other"),
    ],
    "diagnostic_center": [
        ("full_diagnostic_center", "Full Diagnostic Center"),
        ("pathology", "Pathology"),
        ("blood_test_lab", "Blood Test Lab"),
        ("imaging_center", "Imaging Center"),
        ("home_sample_collection", "Home Sample Collection"),
    ],
    "imaging_center": [
        ("mri", "MRI"),
        ("ct_scan", "CT Scan"),
        ("xray", "X-Ray"),
        ("ultrasound", "Ultrasound"),
        ("mammography", "Mammography"),
        ("dexa_scan", "DEXA Scan"),
        ("pet_ct", "PET-CT"),
    ],
    "physiotherapy_rehab": [
        ("physiotherapy", "Physiotherapy"),
        ("neuro_rehabilitation", "Neuro Rehabilitation"),
        ("sports_rehabilitation", "Sports Rehabilitation"),
        ("cardiac_rehabilitation", "Cardiac Rehabilitation"),
        ("occupational_therapy", "Occupational Therapy"),
        ("speech_therapy", "Speech Therapy"),
    ],
}

# Every remaining business type: a single category option matching the type
# itself, so the "Business category" dropdown is never empty.
_TYPES_WITH_BREAKDOWN = set(CATEGORIES_BY_TYPE)
for _slug, _label in BUSINESS_TYPES:
    if _slug not in _TYPES_WITH_BREAKDOWN:
        CATEGORIES_BY_TYPE[_slug] = [(_slug, _label)]

# Pre round-22 business_category values (the old solo_doctor/clinic/hospital
# size-classification). Kept valid indefinitely: orgs registered before this
# round still carry these, and existing tests/integrations register with
# them, so they must keep passing validation even though the Register page
# no longer offers them as options going forward.
LEGACY_BUSINESS_CATEGORIES = {"solo_doctor", "clinic", "hospital"}

ALL_VALID_BUSINESS_CATEGORIES = set(LEGACY_BUSINESS_CATEGORIES)
for _categories in CATEGORIES_BY_TYPE.values():
    ALL_VALID_BUSINESS_CATEGORIES.update(slug for slug, _label in _categories)

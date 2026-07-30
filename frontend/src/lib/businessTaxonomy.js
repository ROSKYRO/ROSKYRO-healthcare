// The registration-time "Business type" / "Business category" taxonomy.
// Hand-kept mirror of backend/app/utils/business_taxonomy.py -- same slugs,
// same structure, same order. There's no shared build step between the two
// codebases, so if one changes, the other needs the matching edit.
//
// Round 22: business_type is the broad kind of healthcare organization
// (Hospital, Clinic, Diagnostic Center, Pharmacy, ...); business_category is
// a specialty dropdown that depends on whichever business_type is selected
// (e.g. Hospital -> Cardiac Hospital / Trauma Center / ...; Clinic ->
// Cardiology / Dermatology / ...).

export const BUSINESS_TYPES = [
  ['hospital', 'Hospital'],
  ['clinic', 'Clinic'],
  ['diagnostic_center', 'Diagnostic Center'],
  ['imaging_center', 'Imaging Center'],
  ['pathology_lab', 'Pathology Lab'],
  ['blood_collection_center', 'Blood Collection Center'],
  ['pharmacy', 'Pharmacy'],
  ['physiotherapy_rehab', 'Physiotherapy & Rehabilitation Center'],
  ['home_healthcare_provider', 'Home Healthcare Provider'],
  ['ambulance_service', 'Ambulance Service'],
  ['blood_bank', 'Blood Bank'],
  ['ivf_fertility_center', 'IVF & Fertility Center'],
  ['dialysis_center', 'Dialysis Center'],
  ['vaccination_center', 'Vaccination Center'],
  ['wellness_center', 'Wellness Center'],
  ['eye_care_center', 'Eye Care Center'],
  ['dental_center', 'Dental Center'],
  ['mental_health_center', 'Mental Health Center'],
  ['medical_equipment_supplier', 'Medical Equipment Supplier'],
  ['healthcare_service_provider', 'Healthcare Service Provider'],
  ['other', 'Other'],
];

// business_type slug -> [category slug, category label][], in dropdown order.
// Hospital / Clinic / Diagnostic Center / Imaging Center / Physiotherapy &
// Rehabilitation Center have an explicit specialty breakdown (product-
// specified). Every other type has no requested breakdown yet, so it falls
// back (below) to a single category option matching the type itself -- the
// dropdown still works (never empty) without inventing sub-specialties
// nobody asked for.
const CATEGORIES_BY_TYPE = {
  hospital: [
    ['multi_speciality_hospital', 'Multi-Speciality Hospital'],
    ['super_speciality_hospital', 'Super Speciality Hospital'],
    ['general_hospital', 'General Hospital'],
    ['childrens_hospital', "Children's Hospital"],
    ['womens_hospital', "Women's Hospital"],
    ['cancer_hospital', 'Cancer Hospital'],
    ['cardiac_hospital', 'Cardiac Hospital'],
    ['orthopedic_hospital', 'Orthopedic Hospital'],
    ['eye_hospital', 'Eye Hospital'],
    ['ent_hospital', 'ENT Hospital'],
    ['government_hospital', 'Government Hospital'],
    ['medical_college_hospital', 'Medical College Hospital'],
    ['trauma_center', 'Trauma Center'],
  ],
  clinic: [
    ['general_physician', 'General Physician'],
    ['pediatrics', 'Pediatrics'],
    ['gynecology_obstetrics', 'Gynecology & Obstetrics'],
    ['orthopedics', 'Orthopedics'],
    ['cardiology', 'Cardiology'],
    ['neurology', 'Neurology'],
    ['dermatology', 'Dermatology'],
    ['psychiatry', 'Psychiatry'],
    ['psychology', 'Psychology'],
    ['gastroenterology', 'Gastroenterology'],
    ['pulmonology', 'Pulmonology'],
    ['endocrinology', 'Endocrinology'],
    ['nephrology', 'Nephrology'],
    ['urology', 'Urology'],
    ['oncology', 'Oncology'],
    ['rheumatology', 'Rheumatology'],
    ['ent', 'ENT'],
    ['ophthalmology', 'Ophthalmology'],
    ['dental', 'Dental'],
    ['physiotherapy', 'Physiotherapy'],
    ['ayurveda', 'Ayurveda'],
    ['homeopathy', 'Homeopathy'],
    ['unani', 'Unani'],
    ['siddha', 'Siddha'],
    ['naturopathy', 'Naturopathy'],
    ['cosmetic_aesthetic', 'Cosmetic & Aesthetic'],
    ['pain_management', 'Pain Management'],
    ['diabetology', 'Diabetology'],
    ['other', 'Other'],
  ],
  diagnostic_center: [
    ['full_diagnostic_center', 'Full Diagnostic Center'],
    ['pathology', 'Pathology'],
    ['blood_test_lab', 'Blood Test Lab'],
    ['imaging_center', 'Imaging Center'],
    ['home_sample_collection', 'Home Sample Collection'],
  ],
  imaging_center: [
    ['mri', 'MRI'],
    ['ct_scan', 'CT Scan'],
    ['xray', 'X-Ray'],
    ['ultrasound', 'Ultrasound'],
    ['mammography', 'Mammography'],
    ['dexa_scan', 'DEXA Scan'],
    ['pet_ct', 'PET-CT'],
  ],
  physiotherapy_rehab: [
    ['physiotherapy', 'Physiotherapy'],
    ['neuro_rehabilitation', 'Neuro Rehabilitation'],
    ['sports_rehabilitation', 'Sports Rehabilitation'],
    ['cardiac_rehabilitation', 'Cardiac Rehabilitation'],
    ['occupational_therapy', 'Occupational Therapy'],
    ['speech_therapy', 'Speech Therapy'],
  ],
};

for (const [slug, label] of BUSINESS_TYPES) {
  if (!CATEGORIES_BY_TYPE[slug]) {
    CATEGORIES_BY_TYPE[slug] = [[slug, label]];
  }
}

export { CATEGORIES_BY_TYPE };

export function categoriesForType(businessType) {
  return CATEGORIES_BY_TYPE[businessType] || [[businessType, businessType]];
}

// Pre-round-22 business_category values (the old solo_doctor/clinic/hospital
// size-classification) -- kept in the label map so orgs registered before
// this round still render a readable badge, even though the Register page
// no longer offers them as options going forward.
const LEGACY_BUSINESS_CATEGORY_LABELS = {
  solo_doctor: 'Solo Doctor',
  clinic: 'Clinic',
  hospital: 'Hospital (All Category)',
};

// Flattened category slug -> label, across every business type, merged with
// the legacy labels above. Used anywhere a business_category needs to render
// as a human-readable badge (Dashboard, internal Businesses list) rather
// than as a dropdown.
export const BUSINESS_CATEGORY_LABELS = Object.values(CATEGORIES_BY_TYPE)
  .flat()
  .reduce((acc, [slug, label]) => {
    acc[slug] = label;
    return acc;
  }, { ...LEGACY_BUSINESS_CATEGORY_LABELS });

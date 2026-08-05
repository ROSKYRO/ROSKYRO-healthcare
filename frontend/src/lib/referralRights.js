// Mirrors backend/app/routers/referrals.py's REFERRAL_CREATOR_BUSINESS_TYPES.
// Only these business types have the right to choose/create a referral to a
// partner. Every other business type can still list itself as a CONNECT
// partner (see BecomePartner.jsx, which is deliberately unrestricted) but
// cannot initiate a referral of its own.
//
// "eye_hospital" predates round 22's business-type taxonomy rewrite (see
// lib/businessTaxonomy.js) -- kept so orgs registered under the old taxonomy
// keep their existing right. "eye_care_center" is that type's direct
// equivalent under the new taxonomy's standalone Eye Care Center option
// (an eye-focused org under the new Hospital type already registers with
// business_type "hospital", already covered).
export const REFERRAL_CREATOR_BUSINESS_TYPES = ['clinic', 'hospital', 'eye_hospital', 'eye_care_center'];

export function canCreateReferrals(user) {
  return !!user && REFERRAL_CREATOR_BUSINESS_TYPES.includes(user.businessType);
}

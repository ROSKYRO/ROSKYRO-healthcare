// Mirrors backend/app/routers/referrals.py's REFERRAL_CREATOR_BUSINESS_TYPES.
// Only these business types have the right to choose/create a referral to a
// partner. Every other business type can still list itself as a Networking Marketing
// partner (see BecomePartner.jsx, which is deliberately unrestricted) but
// cannot initiate a referral of its own.
export const REFERRAL_CREATOR_BUSINESS_TYPES = ['clinic', 'hospital', 'eye_hospital'];

export function canCreateReferrals(user) {
  return !!user && REFERRAL_CREATOR_BUSINESS_TYPES.includes(user.businessType);
}

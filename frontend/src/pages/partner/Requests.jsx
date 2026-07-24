import ReferralsList from '../shared/ReferralsList';

export default function PartnerRequests() {
  return (
    <ReferralsList
      title="Referral Requests"
      subtitle="Referrals sent to you by healthcare businesses in the ROSKYRO network."
      basePath="/partner/requests"
    />
  );
}

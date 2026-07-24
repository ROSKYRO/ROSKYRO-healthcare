import ReferralsList from '../shared/ReferralsList';

export default function Referrals() {
  return (
    <ReferralsList
      title="Referral Network"
      subtitle="Send patients to trusted partners and track every referral end to end."
      basePath="/app/referrals"
      newPath="/app/referrals/new"
      showCreate
    />
  );
}

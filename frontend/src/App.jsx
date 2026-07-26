import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';

import Landing from './pages/Landing';
import Login from './pages/Login';
import Register from './pages/Register';
import Pricing from './pages/Pricing';
import Services from './pages/Services';
import About from './pages/About';
import Contact from './pages/Contact';
import FAQ from './pages/FAQ';
import PrivacyPolicy from './pages/legal/PrivacyPolicy';
import TermsConditions from './pages/legal/TermsConditions';
import RefundPolicy from './pages/legal/RefundPolicy';
import CookiePolicy from './pages/legal/CookiePolicy';
import Disclaimer from './pages/legal/Disclaimer';
import PublicBooking from './pages/PublicBooking';

import CustomerDashboard from './pages/customer/Dashboard';
import Referrals from './pages/customer/Referrals';
import ReferralNew from './pages/customer/ReferralNew';
import PartnerDirectory from './pages/customer/PartnerDirectory';
import Partnerships from './pages/customer/Partnerships';
import BecomePartner from './pages/customer/BecomePartner';
import Appointments from './pages/customer/Appointments';
import Reviews from './pages/customer/Reviews';
import Approvals from './pages/customer/Approvals';
import Reports from './pages/customer/Reports';
import Team from './pages/customer/Team';
import Plans from './pages/customer/Plans';
import Patients from './pages/customer/Patients';
import PatientDetail from './pages/customer/PatientDetail';
import Queue from './pages/customer/Queue';
import Followups from './pages/customer/Followups';
import Billing from './pages/customer/Billing';
import Whatsapp from './pages/customer/Whatsapp';
import GrowthHub from './pages/customer/GrowthHub';
import BookingSettings from './pages/customer/BookingSettings';
import CustomerSettlements from './pages/customer/Settlements';

import PartnerDashboard from './pages/partner/Dashboard';
import PartnerRequests from './pages/partner/Requests';
import PartnerPartnerships from './pages/partner/Partnerships';
import Wallet from './pages/partner/Wallet';

import InternalDashboard from './pages/internal/Dashboard';
import Tasks from './pages/internal/Tasks';
import AllReferrals from './pages/internal/AllReferrals';
import Organizations from './pages/internal/Organizations';
import PartnerVerification from './pages/internal/PartnerVerification';
import InternalSettlements from './pages/internal/Settlements';
import MarketingPayouts from './pages/internal/MarketingPayouts';
import SubscriptionRenewals from './pages/internal/SubscriptionRenewals';
import AdminWallet from './pages/internal/AdminWallet';
import Roster from './pages/internal/Roster';
import PricingManagement from './pages/internal/PricingManagement';
import PasswordRequests from './pages/internal/PasswordRequests';
import WhatsappQueue from './pages/internal/WhatsappQueue';

import ReferralDetail from './pages/shared/ReferralDetail';

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/pricing" element={<Pricing />} />
          <Route path="/services" element={<Services />} />
          <Route path="/about" element={<About />} />
          <Route path="/contact" element={<Contact />} />
          <Route path="/faq" element={<FAQ />} />
          <Route path="/privacy-policy" element={<PrivacyPolicy />} />
          <Route path="/terms-conditions" element={<TermsConditions />} />
          <Route path="/refund-policy" element={<RefundPolicy />} />
          <Route path="/cookie-policy" element={<CookiePolicy />} />
          <Route path="/disclaimer" element={<Disclaimer />} />
          <Route path="/book/:orgId" element={<PublicBooking />} />

          {/* Customer (healthcare business) app */}
          <Route path="/app" element={<ProtectedRoute allow={['customer']}><CustomerDashboard /></ProtectedRoute>} />
          <Route path="/app/referrals" element={<ProtectedRoute allow={['customer']}><Referrals /></ProtectedRoute>} />
          <Route path="/app/referrals/new" element={<ProtectedRoute allow={['customer']}><ReferralNew /></ProtectedRoute>} />
          <Route path="/app/referrals/:id" element={<ProtectedRoute allow={['customer']}><ReferralDetail basePath="/app/referrals" /></ProtectedRoute>} />
          <Route path="/app/become-partner" element={<ProtectedRoute allow={['customer']}><BecomePartner /></ProtectedRoute>} />
          <Route path="/app/partners" element={<ProtectedRoute allow={['customer']}><PartnerDirectory /></ProtectedRoute>} />
          <Route path="/app/partnerships" element={<ProtectedRoute allow={['customer']}><Partnerships /></ProtectedRoute>} />
          <Route path="/app/settlements" element={<ProtectedRoute allow={['customer']}><CustomerSettlements /></ProtectedRoute>} />
          <Route path="/app/appointments" element={<ProtectedRoute allow={['customer']}><Appointments /></ProtectedRoute>} />
          <Route path="/app/reviews" element={<ProtectedRoute allow={['customer']}><Reviews /></ProtectedRoute>} />
          <Route path="/app/approvals" element={<ProtectedRoute allow={['customer']}><Approvals /></ProtectedRoute>} />
          <Route path="/app/reports" element={<ProtectedRoute allow={['customer']}><Reports /></ProtectedRoute>} />
          <Route path="/app/team" element={<ProtectedRoute allow={['customer']}><Team /></ProtectedRoute>} />
          <Route path="/app/plans" element={<ProtectedRoute allow={['customer']}><Plans /></ProtectedRoute>} />
          <Route path="/app/patients" element={<ProtectedRoute allow={['customer']}><Patients /></ProtectedRoute>} />
          <Route path="/app/patients/:id" element={<ProtectedRoute allow={['customer']}><PatientDetail /></ProtectedRoute>} />
          <Route path="/app/queue" element={<ProtectedRoute allow={['customer']}><Queue /></ProtectedRoute>} />
          <Route path="/app/followups" element={<ProtectedRoute allow={['customer']}><Followups /></ProtectedRoute>} />
          <Route path="/app/billing" element={<ProtectedRoute allow={['customer']}><Billing /></ProtectedRoute>} />
          <Route path="/app/whatsapp" element={<ProtectedRoute allow={['customer']}><Whatsapp /></ProtectedRoute>} />
          <Route path="/app/booking" element={<ProtectedRoute allow={['customer']}><BookingSettings /></ProtectedRoute>} />
          <Route path="/app/growth" element={<ProtectedRoute allow={['customer']}><GrowthHub /></ProtectedRoute>} />

          {/* Partner portal */}
          <Route path="/partner" element={<ProtectedRoute allow={['partner']}><PartnerDashboard /></ProtectedRoute>} />
          <Route path="/partner/requests" element={<ProtectedRoute allow={['partner']}><PartnerRequests /></ProtectedRoute>} />
          <Route path="/partner/requests/:id" element={<ProtectedRoute allow={['partner']}><ReferralDetail basePath="/partner/requests" /></ProtectedRoute>} />
          <Route path="/partner/partnerships" element={<ProtectedRoute allow={['partner']}><PartnerPartnerships /></ProtectedRoute>} />
          <Route path="/partner/wallet" element={<ProtectedRoute allow={['partner']}><Wallet /></ProtectedRoute>} />

          {/* Internal ROSKYRO team dashboard */}
          <Route path="/team" element={<ProtectedRoute allow={['internal']}><InternalDashboard /></ProtectedRoute>} />
          <Route path="/team/tasks" element={<ProtectedRoute allow={['internal']}><Tasks /></ProtectedRoute>} />
          <Route path="/team/referrals" element={<ProtectedRoute allow={['internal']}><AllReferrals /></ProtectedRoute>} />
          <Route path="/team/referrals/:id" element={<ProtectedRoute allow={['internal']}><ReferralDetail basePath="/team/referrals" /></ProtectedRoute>} />
          <Route path="/team/organizations" element={<ProtectedRoute allow={['internal']}><Organizations /></ProtectedRoute>} />
          <Route path="/team/partner-verification" element={<ProtectedRoute allow={['internal']}><PartnerVerification /></ProtectedRoute>} />
          <Route path="/team/settlements" element={<ProtectedRoute allow={['internal']}><InternalSettlements /></ProtectedRoute>} />
          <Route path="/team/marketing-payouts" element={<ProtectedRoute allow={['internal']}><MarketingPayouts /></ProtectedRoute>} />
          <Route path="/team/subscription-renewals" element={<ProtectedRoute allow={['internal']}><SubscriptionRenewals /></ProtectedRoute>} />
          <Route path="/team/whatsapp-queue" element={<ProtectedRoute allow={['internal']}><WhatsappQueue /></ProtectedRoute>} />
          <Route path="/team/wallet" element={<ProtectedRoute allow={['internal']}><AdminWallet /></ProtectedRoute>} />
          <Route path="/team/roster" element={<ProtectedRoute allow={['internal']}><Roster /></ProtectedRoute>} />
          <Route path="/team/pricing" element={<ProtectedRoute allow={['internal']}><PricingManagement /></ProtectedRoute>} />
          <Route path="/team/password-requests" element={<ProtectedRoute allow={['internal']}><PasswordRequests /></ProtectedRoute>} />

          <Route path="*" element={<Landing />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

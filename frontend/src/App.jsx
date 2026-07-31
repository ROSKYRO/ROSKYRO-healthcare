import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import { PageLoading } from './components/ui';

// PERFORMANCE (round 18): every one of the 60+ page components below used to
// be a plain static `import`, which meant webpack emitted ONE bundle
// containing the entire application -- all three app shells, every internal
// admin screen, every legal page. A patient scanning a clinic's QR code on
// mobile data downloaded and parsed the ROSKYRO internal settlements console
// before the booking form could render. Nothing about how any page BEHAVES
// changes here: React.lazy() only defers *when* the code for a route is
// fetched (on first navigation to it) instead of *whether* it is fetched.
// Same components, same routes, same props.
//
// Deliberately kept STATIC (i.e. in the main bundle, no extra round-trip):
//   - Landing, Login, Pricing -- the three most common first paint for a
//     visitor; lazy-loading these would ADD a network hop to the very page
//     that decides whether someone bounces.
//   - PublicBooking -- the QR-code destination. This is the single most
//     latency-sensitive screen in the product (a patient standing in a
//     clinic, on a phone, on cellular), so it must never wait on a second
//     chunk fetch.
//
// The <Suspense> fallback below is PageLoading -- the exact same spinner
// ProtectedRoute already shows while the auth check resolves, so a
// first-visit-to-a-route chunk fetch looks identical to the loading state
// users already see rather than flashing something new.

import Landing from './pages/Landing';
import Login from './pages/Login';
import Pricing from './pages/Pricing';
import PublicBooking from './pages/PublicBooking';

const Register = lazy(() => import('./pages/Register'));
const Services = lazy(() => import('./pages/Services'));
const About = lazy(() => import('./pages/About'));
const Contact = lazy(() => import('./pages/Contact'));
const FAQ = lazy(() => import('./pages/FAQ'));
const PrivacyPolicy = lazy(() => import('./pages/legal/PrivacyPolicy'));
const TermsConditions = lazy(() => import('./pages/legal/TermsConditions'));
const RefundPolicy = lazy(() => import('./pages/legal/RefundPolicy'));
const CookiePolicy = lazy(() => import('./pages/legal/CookiePolicy'));
const Disclaimer = lazy(() => import('./pages/legal/Disclaimer'));

const CustomerDashboard = lazy(() => import('./pages/customer/Dashboard'));
const Referrals = lazy(() => import('./pages/customer/Referrals'));
const ReferralNew = lazy(() => import('./pages/customer/ReferralNew'));
const PartnerDirectory = lazy(() => import('./pages/customer/PartnerDirectory'));
const Partnerships = lazy(() => import('./pages/customer/Partnerships'));
const BecomePartner = lazy(() => import('./pages/customer/BecomePartner'));
const Appointments = lazy(() => import('./pages/customer/Appointments'));
const Reviews = lazy(() => import('./pages/customer/Reviews'));
const Approvals = lazy(() => import('./pages/customer/Approvals'));
const Reports = lazy(() => import('./pages/customer/Reports'));
const Team = lazy(() => import('./pages/customer/Team'));
const Plans = lazy(() => import('./pages/customer/Plans'));
const Patients = lazy(() => import('./pages/customer/Patients'));
const PatientDetail = lazy(() => import('./pages/customer/PatientDetail'));
const Queue = lazy(() => import('./pages/customer/Queue'));
const Followups = lazy(() => import('./pages/customer/Followups'));
const Billing = lazy(() => import('./pages/customer/Billing'));
const Whatsapp = lazy(() => import('./pages/customer/Whatsapp'));
const GrowthHub = lazy(() => import('./pages/customer/GrowthHub'));
const BookingSettings = lazy(() => import('./pages/customer/BookingSettings'));
const CustomerSettlements = lazy(() => import('./pages/customer/Settlements'));

const PartnerDashboard = lazy(() => import('./pages/partner/Dashboard'));
const PartnerRequests = lazy(() => import('./pages/partner/Requests'));
const PartnerPartnerships = lazy(() => import('./pages/partner/Partnerships'));
const Wallet = lazy(() => import('./pages/partner/Wallet'));
const PartnerPlans = lazy(() => import('./pages/partner/Plans'));

const InternalDashboard = lazy(() => import('./pages/internal/Dashboard'));
const Tasks = lazy(() => import('./pages/internal/Tasks'));
const AllReferrals = lazy(() => import('./pages/internal/AllReferrals'));
const Organizations = lazy(() => import('./pages/internal/Organizations'));
const PartnerVerification = lazy(() => import('./pages/internal/PartnerVerification'));
const InternalSettlements = lazy(() => import('./pages/internal/Settlements'));
const MarketingPayouts = lazy(() => import('./pages/internal/MarketingPayouts'));
const SubscriptionRenewals = lazy(() => import('./pages/internal/SubscriptionRenewals'));
const PaymentConfirmations = lazy(() => import('./pages/internal/PaymentConfirmations'));
const AdminWallet = lazy(() => import('./pages/internal/AdminWallet'));
const Roster = lazy(() => import('./pages/internal/Roster'));
const ManageTeam = lazy(() => import('./pages/internal/ManageTeam'));
const PricingManagement = lazy(() => import('./pages/internal/PricingManagement'));
const PasswordRequests = lazy(() => import('./pages/internal/PasswordRequests'));
const WhatsappQueue = lazy(() => import('./pages/internal/WhatsappQueue'));
const ResetDemoData = lazy(() => import('./pages/internal/ResetDemoData'));

const ReferralDetail = lazy(() => import('./pages/shared/ReferralDetail'));

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Suspense fallback={<PageLoading />}>
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
          <Route path="/partner/plans" element={<ProtectedRoute allow={['partner']}><PartnerPlans /></ProtectedRoute>} />

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
          <Route path="/team/payment-confirmations" element={<ProtectedRoute allow={['internal']}><PaymentConfirmations /></ProtectedRoute>} />
          <Route path="/team/whatsapp-queue" element={<ProtectedRoute allow={['internal']}><WhatsappQueue /></ProtectedRoute>} />
          <Route path="/team/wallet" element={<ProtectedRoute allow={['internal']}><AdminWallet /></ProtectedRoute>} />
          <Route path="/team/roster" element={<ProtectedRoute allow={['internal']}><Roster /></ProtectedRoute>} />
          <Route path="/team/manage-team" element={<ProtectedRoute allow={['internal']}><ManageTeam /></ProtectedRoute>} />
          <Route path="/team/pricing" element={<ProtectedRoute allow={['internal']}><PricingManagement /></ProtectedRoute>} />
          <Route path="/team/password-requests" element={<ProtectedRoute allow={['internal']}><PasswordRequests /></ProtectedRoute>} />
          <Route path="/team/reset-demo-data" element={<ProtectedRoute allow={['internal']}><ResetDemoData /></ProtectedRoute>} />

          <Route path="*" element={<Landing />} />
        </Routes>
        </Suspense>
      </AuthProvider>
    </BrowserRouter>
  );
}

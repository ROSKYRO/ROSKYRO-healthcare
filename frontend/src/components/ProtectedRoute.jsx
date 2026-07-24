import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { PageLoading } from './ui';
import Layout from './Layout';

export default function ProtectedRoute({ children, allow }) {
  const { user, loading } = useAuth();

  if (loading) return <PageLoading />;
  if (!user) return <Navigate to="/login" replace />;
  if (allow && !allow.includes(user.appShell)) {
    const home = { customer: '/app', partner: '/partner', internal: '/team' }[user.appShell] || '/login';
    return <Navigate to={home} replace />;
  }

  return <Layout>{children}</Layout>;
}

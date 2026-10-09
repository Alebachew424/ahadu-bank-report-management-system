import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ProtectedRoute } from './ProtectedRoute';
import { Login } from '../pages/auth/Login';
import { Register } from '../pages/auth/Register';
import { RequesterDashboard } from '../pages/dashboard/RequesterDashboard';
import { PerformanceDashboard } from '../pages/dashboard/PerformanceDashboard';
import { RequestList } from '../pages/requests/RequestList';
import { RequestCreate } from '../pages/requests/RequestCreate';
import { RequestDetail } from '../pages/requests/RequestDetail';
import Layout from '../components/layout/Layout';
import { UserManagement } from '../pages/admin/UserManagement';
import { AuditLog } from '../pages/admin/AuditLog';
import { Schedules } from '../pages/schedules/Schedules';
import { CommunicationCenter } from '../pages/communications/CommunicationCenter';

export function AppRoutes() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<Layout />}>
            <Route path="/" element={<RequesterDashboard />} />
            <Route path="/requests" element={<RequestList />} />
            <Route path="/requests/create" element={<RequestCreate />} />
            <Route path="/requests/:id" element={<RequestDetail />} />
            <Route path="/performance" element={<PerformanceDashboard />} />
            <Route path="/users" element={<UserManagement />} />
            <Route path="/audit" element={<AuditLog />} />
            <Route path="/schedules" element={<Schedules />} />
            <Route path="/communications" element={<CommunicationCenter />} />
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

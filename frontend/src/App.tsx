/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { Routes, Route, Navigate } from 'react-router-dom';
import { AppLayout } from './components/layout/AppLayout';
import { OverviewPage } from './pages/OverviewPage';
import { NeedsTriagePage } from './pages/NeedsTriagePage';
import { MapPage } from './pages/MapPage';
import { VolunteersPage } from './pages/VolunteersPage';
import { HouseholdsPage } from './pages/HouseholdsPage';
import { SettingsPage } from './pages/SettingsPage';
import { TasksPage } from './pages/TasksPage';
import { InboxPage } from './pages/InboxPage';
import { ReportsPage } from './pages/ReportsPage';
import { SignInPage } from './pages/SignInPage';
import { SignUpPage } from './pages/SignUpPage';
import { IntakeRegistrationPage } from './pages/IntakeRegistrationPage';
import { VolunteerRegistrationPage } from './pages/VolunteerRegistrationPage';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { IngestionPage } from './pages/IngestionPage';
import { PriorityQueuePage } from './pages/PriorityQueuePage';
import { TaskDispatchPage } from './pages/TaskDispatchPage';
import { AnalyticsDashboardPage } from './pages/AnalyticsDashboardPage';
import { FunderReportPage } from './pages/FunderReportPage';
import { WeightsSettingsPage } from './pages/WeightsSettingsPage';
import { AdminTenantsPage } from './pages/AdminTenantsPage';
import { FieldWorkerHomePage } from './pages/field/FieldWorkerHomePage';
import HouseholdSearchPage from './pages/field/HouseholdSearchPage';
import { HouseholdRegistrationPage } from './pages/field/HouseholdRegistrationPage';
import { NeedReportPage } from './pages/field/NeedReportPage';
import { VolunteerHomePage } from './pages/field/VolunteerHomePage';

import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';

export default function App() {
  return (
    <>
      <ToastContainer position="top-right" autoClose={3000} hideProgressBar theme="colored" />
      <Routes>
      <Route path="/auth/signin" element={<SignInPage />} />
      <Route path="/auth/signup" element={<SignUpPage />} />
      <Route path="/" element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
        <Route index element={<OverviewPage />} />
        <Route path="needs" element={<ProtectedRoute requiredPermission="needs:read"><NeedsTriagePage /></ProtectedRoute>} />
        <Route path="tasks" element={<ProtectedRoute requiredPermission="tasks:read"><TasksPage /></ProtectedRoute>} />
        <Route path="tasks/dispatch" element={<ProtectedRoute requiredPermission="tasks:*"><TaskDispatchPage /></ProtectedRoute>} />
        <Route path="map" element={<MapPage />} />
        <Route path="volunteers" element={<ProtectedRoute requiredPermission="volunteers:*"><VolunteersPage /></ProtectedRoute>} />
        <Route path="volunteers/register" element={<ProtectedRoute requiredPermission="volunteers:*"><VolunteerRegistrationPage /></ProtectedRoute>} />
        <Route path="households" element={<ProtectedRoute requiredPermission="households:read"><HouseholdsPage /></ProtectedRoute>} />
        <Route path="households/intake" element={<ProtectedRoute requiredPermission="households:create"><IntakeRegistrationPage /></ProtectedRoute>} />
        <Route path="households/intake/:id" element={<ProtectedRoute requiredPermission="households:*"><IntakeRegistrationPage /></ProtectedRoute>} />
        <Route path="ingestion" element={<ProtectedRoute requiredPermission="needs:create"><IngestionPage /></ProtectedRoute>} />
        <Route path="priority-queue" element={<ProtectedRoute requiredPermission="needs:read"><PriorityQueuePage /></ProtectedRoute>} />
        <Route path="analytics" element={<ProtectedRoute requiredPermission="analytics:read"><AnalyticsDashboardPage /></ProtectedRoute>} />
        <Route path="funder" element={<ProtectedRoute requiredPermission="analytics:read"><FunderReportPage /></ProtectedRoute>} />
        <Route path="weights" element={<ProtectedRoute requiredPermission="needs:*"><WeightsSettingsPage /></ProtectedRoute>} />
        <Route path="inbox" element={<InboxPage />} />
        <Route path="reports" element={<ProtectedRoute requiredPermission="analytics:read"><ReportsPage /></ProtectedRoute>} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="tenants" element={<ProtectedRoute requiredPermission="tenants"><AdminTenantsPage /></ProtectedRoute>} />
        
        {/* Field Worker Routes */}
        <Route path="field">
          <Route index element={<FieldWorkerHomePage />} />
          <Route path="report" element={<HouseholdSearchPage />} />
          <Route path="report/need" element={<NeedReportPage />} />
          <Route path="households/new" element={<HouseholdRegistrationPage />} />
          <Route path="tasks" element={<VolunteerHomePage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
    </>
  );
}

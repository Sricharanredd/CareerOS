import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/layout/AppShell";
import { RequireAuth } from "@/layout/RequireAuth";
import { AnalyticsPage } from "@/pages/AnalyticsPage";
import { AnalyzerPage } from "@/pages/AnalyzerPage";
import { ApplicationsPage } from "@/pages/ApplicationsPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { InterviewsPage } from "@/pages/InterviewsPage";
import { JobDescriptionsPage } from "@/pages/JobDescriptionsPage";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { ResumesPage } from "@/pages/ResumesPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { TasksPage } from "@/pages/TasksPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="applications" element={<ApplicationsPage />} />
        <Route path="job-descriptions" element={<JobDescriptionsPage />} />
        <Route path="resumes" element={<ResumesPage />} />
        <Route path="analyzer" element={<AnalyzerPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="interviews" element={<InterviewsPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

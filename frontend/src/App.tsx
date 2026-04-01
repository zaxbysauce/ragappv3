import { BrowserRouter, Routes, Route, Navigate, useNavigate } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { PageShell } from "@/components/layout/PageShell";
import ChatPageRedesigned from "@/pages/ChatPageRedesigned";
import ChatShell from "@/pages/ChatShell";
import DocumentsPage from "@/pages/DocumentsPage";
import MemoryPage from "@/pages/MemoryPage";
import VaultsPage from "@/pages/VaultsPage";
import SettingsPage from "@/pages/SettingsPage";
import LoginPage from "@/pages/LoginPage";
import SetupPage from "@/pages/SetupPage";
import RegisterPage from "@/pages/RegisterPage";
import AdminUsersPage from "@/pages/AdminUsersPage";
import AdminGroupsPage from "@/pages/AdminGroupsPage";
import OrgsPage from "@/pages/OrgsPage";
import ProfilePage from "@/pages/ProfilePage";
import { useHealthCheck } from "@/hooks/useHealthCheck";
import { useEffect } from "react";
import { useAuthStore } from "@/stores/useAuthStore";

// Main app shell wrapper that provides the navigation and page layout
function MainAppShell({ children }: { children: React.ReactNode }) {
  const health = useHealthCheck({ pollInterval: 30000 });
  const navigate = useNavigate();

  const handleItemSelect = (id: string) => {
    switch (id) {
      case "chat":
        navigate("/chat");
        break;
      case "documents":
        navigate("/documents");
        break;
      case "memory":
        navigate("/memory");
        break;
      case "vaults":
        navigate("/vaults");
        break;
      case "settings":
        navigate("/settings");
        break;
      case "groups":
        navigate("/admin/groups");
        break;
      case "users":
        navigate("/admin/users");
        break;
      case "organizations":
        navigate("/admin/organizations");
        break;
      default:
        navigate("/documents");
    }
  };

  return (
    <PageShell
      activeItem="documents" // Default value, will be overridden by route
      onItemSelect={handleItemSelect}
      healthStatus={health}
    >
      {children}
    </PageShell>
  );
}

function App() {
  const initAuth = useAuthStore((state) => state.init);

  useEffect(() => {
    initAuth();
  }, [initAuth]);

  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/setup" element={<SetupPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/chat" element={<ProtectedRoute><ChatShell /></ProtectedRoute>} />
            <Route path="/chat/:sessionId" element={<ProtectedRoute><ChatShell /></ProtectedRoute>} />
            <Route path="/chat/redesign" element={<ProtectedRoute><ChatPageRedesigned /></ProtectedRoute>} />

            {/* Main app pages with shell */}
            <Route
              path="/documents"
              element={
                <ProtectedRoute>
                  <MainAppShell>
                    <DocumentsPage />
                  </MainAppShell>
                </ProtectedRoute>
              }
            />
            <Route
              path="/memory"
              element={
                <ProtectedRoute>
                  <MainAppShell>
                    <MemoryPage />
                  </MainAppShell>
                </ProtectedRoute>
              }
            />
            <Route
              path="/vaults"
              element={
                <ProtectedRoute>
                  <MainAppShell>
                    <VaultsPage />
                  </MainAppShell>
                </ProtectedRoute>
              }
            />
            <Route
              path="/settings"
              element={
                <ProtectedRoute>
                  <MainAppShell>
                    <SettingsPage />
                  </MainAppShell>
                </ProtectedRoute>
              }
            />

            {/* Admin pages */}
            <Route
              path="/admin/users"
              element={
                <ProtectedRoute>
                  <MainAppShell>
                    <AdminUsersPage />
                  </MainAppShell>
                </ProtectedRoute>
              }
            />
            <Route
              path="/admin/groups"
              element={
                <ProtectedRoute>
                  <MainAppShell>
                    <AdminGroupsPage />
                  </MainAppShell>
                </ProtectedRoute>
              }
            />
            <Route
              path="/admin/organizations"
              element={
                <ProtectedRoute>
                  <MainAppShell>
                    <OrgsPage />
                  </MainAppShell>
                </ProtectedRoute>
              }
            />

            <Route path="/profile" element={<ProtectedRoute><ProfilePage /></ProtectedRoute>} />

            {/* Redirect root to documents */}
            <Route path="/" element={<Navigate to="/documents" replace />} />

            {/* Default redirect to documents */}
            <Route
              path="/*"
              element={
                <ProtectedRoute>
                  <MainAppShell>
                    <DocumentsPage />
                  </MainAppShell>
                </ProtectedRoute>
              }
            />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
}

export default App;

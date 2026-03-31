import { BrowserRouter, Routes, Route } from "react-router-dom";
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
import { useState, useEffect } from "react";
import { useAuthStore } from "@/stores/useAuthStore";

type PageId = "documents" | "memory" | "vaults" | "settings";

const pages: Record<PageId, React.ComponentType> = {
  documents: DocumentsPage,
  memory: MemoryPage,
  vaults: VaultsPage,
  settings: SettingsPage,
};

function MainApp() {
  const [activePage, setActivePage] = useState<PageId>("documents");
  const health = useHealthCheck({ pollInterval: 30000 });

  const CurrentPage = pages[activePage];

  return (
    <PageShell
      activeItem={activePage}
      onItemSelect={(id) => setActivePage(id as PageId)}
      healthStatus={health}
    >
      <CurrentPage />
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
            <Route path="/admin/users" element={<ProtectedRoute><AdminUsersPage /></ProtectedRoute>} />
            <Route path="/admin/groups" element={<ProtectedRoute><AdminGroupsPage /></ProtectedRoute>} />
            <Route path="/admin/organizations" element={<ProtectedRoute><OrgsPage /></ProtectedRoute>} />
            <Route path="/profile" element={<ProtectedRoute><ProfilePage /></ProtectedRoute>} />
            <Route
              path="/chat/redesign"
              element={
                <ProtectedRoute>
                  <PageShell
                    activeItem="chat"
                    onItemSelect={() => {}}
                    healthStatus={{ backend: true, embeddings: true, chat: true, loading: false, lastChecked: null }}
                  >
                    <ChatPageRedesigned />
                  </PageShell>
                </ProtectedRoute>
              }
            />
            <Route
              path="/*"
              element={
                <ProtectedRoute>
                  <MainApp />
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

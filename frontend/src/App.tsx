import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { PageShell } from "@/components/layout/PageShell";
import ChatPage from "@/pages/ChatPage";
import ChatPageRedesigned from "@/pages/ChatPageRedesigned";
import DocumentsPage from "@/pages/DocumentsPage";
import MemoryPage from "@/pages/MemoryPage";
import VaultsPage from "@/pages/VaultsPage";
import SettingsPage from "@/pages/SettingsPage";
import LoginPage from "@/pages/LoginPage";
import { useHealthCheck } from "@/hooks/useHealthCheck";
import { useState } from "react";

type PageId = "chat" | "documents" | "memory" | "vaults" | "settings";

const pages: Record<PageId, React.ComponentType> = {
  chat: ChatPage,
  documents: DocumentsPage,
  memory: MemoryPage,
  vaults: VaultsPage,
  settings: SettingsPage,
};

function MainApp() {
  const [activePage, setActivePage] = useState<PageId>("chat");
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
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
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

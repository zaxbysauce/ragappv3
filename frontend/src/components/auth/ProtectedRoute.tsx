import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { useAuthStore } from "@/stores/useAuthStore";
import { Loader2 } from "lucide-react";

interface ProtectedRouteProps {
  children: React.ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const location = useLocation();

  // Check both legacy AuthContext and new JWT auth store
  const { isAuthenticated: contextAuth, isLoading: contextLoading } = useAuth();
  const {
    isAuthenticated: storeAuth,
    isLoading: storeLoading,
    needsSetup,
  } = useAuthStore();

  const isAuthenticated = contextAuth || storeAuth;
  const isLoading = contextLoading || storeLoading;

  if (isLoading) {
    return (
      <div className="flex h-screen w-full items-center justify-center">
        <Loader2
          className="h-8 w-8 animate-spin text-muted-foreground"
          role="status"
          aria-live="polite"
        />
      </div>
    );
  }

  // If setup is needed, redirect to setup page with return location
  if (needsSetup) {
    return <Navigate to="/setup" state={{ from: location }} replace />;
  }

  // If not authenticated, redirect to login with return location
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

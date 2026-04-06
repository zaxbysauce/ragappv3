import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore } from "@/stores/useAuthStore";
import { Loader2 } from "lucide-react";

interface ProtectedRouteProps {
  children: React.ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const location = useLocation();

  // H-10 fix: Use only the JWT auth store — legacy AuthContext OR removed
  const { isAuthenticated, isLoading, isInitialized, needsSetup } = useAuthStore();

  // Show loading while auth state or setup check is still initializing
  // RT-02 fix: wait for init() to complete before making auth decisions
  if (isLoading || !isInitialized || needsSetup === null) {
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
  if (needsSetup === true) {
    return <Navigate to="/setup" state={{ from: location }} replace />;
  }

  // If not authenticated, redirect to login with return location
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

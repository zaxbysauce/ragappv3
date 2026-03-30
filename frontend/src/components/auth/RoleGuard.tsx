import { Navigate } from "react-router-dom";
import { useAuthStore } from "@/stores/useAuthStore";
import { Loader2 } from "lucide-react";
import type { ReactNode } from "react";

// Role hierarchy: higher number = more permissions
type Role = "superadmin" | "admin" | "member" | "viewer";

const ROLE_LEVELS: Record<Role, number> = {
  viewer: 0,
  member: 1,
  admin: 2,
  superadmin: 3,
};

interface RoleGuardProps {
  allowedRoles: Role[];
  children: ReactNode;
  fallback?: ReactNode;
  inline?: boolean;
}

function hasRequiredRole(userRole: string | undefined, requiredRoles: Role[]): boolean {
  if (!userRole) return false;
  if (!(userRole in ROLE_LEVELS)) return false;
  const userLevel = ROLE_LEVELS[userRole as Role];
  return requiredRoles.some((role) => userLevel >= ROLE_LEVELS[role]);
}

export function RoleGuard({
  allowedRoles,
  children,
  fallback,
  inline = false,
}: RoleGuardProps) {
  const { user, isAuthenticated, isLoading } = useAuthStore();

  if (isLoading) {
    const spinner = (
      <Loader2
        className="h-6 w-6 animate-spin text-muted-foreground"
        role="status"
        aria-live="polite"
      />
    );

    if (inline) {
      return <span className="inline-flex items-center">{spinner}</span>;
    }

    return (
      <div className="flex h-full w-full items-center justify-center">
        {spinner}
      </div>
    );
  }

  // Not authenticated
  if (!isAuthenticated) {
    if (fallback !== undefined) {
      return <>{fallback}</>;
    }
    return <Navigate to="/login" replace />;
  }

  // Check role permissions
  const userRole = user?.role;
  if (!hasRequiredRole(userRole, allowedRoles)) {
    if (fallback !== undefined) {
      return <>{fallback}</>;
    }
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}

// Convenience component for admin-level access
export function AdminGuard({
  children,
  fallback,
  inline,
}: Omit<RoleGuardProps, "allowedRoles">) {
  return (
    <RoleGuard allowedRoles={["admin", "superadmin"]} fallback={fallback} inline={inline}>
      {children}
    </RoleGuard>
  );
}

// Convenience component for superadmin-only access
export function SuperAdminGuard({
  children,
  fallback,
  inline,
}: Omit<RoleGuardProps, "allowedRoles">) {
  return (
    <RoleGuard allowedRoles={["superadmin"]} fallback={fallback} inline={inline}>
      {children}
    </RoleGuard>
  );
}

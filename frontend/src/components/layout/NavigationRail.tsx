import { MessageSquare, FileText, Brain, Settings, Database, Users, UserCog, Building2, UserCircle, Sun, Moon, BookOpen } from "lucide-react";
import { useThemeStore } from "@/stores/useThemeStore";
import { useAuthStore } from "@/stores/useAuthStore";
import { cn } from "@/lib/utils";
import { NavLink, useLocation } from "react-router-dom";
import type { NavItemId, NavigationProps } from "./navigationTypes";

// Re-export types for backward compatibility
export type { NavItemId, NavigationProps };

interface NavConfigItem {
  id: NavItemId;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  to: string;
  adminOnly?: boolean;
}

const navItems: NavConfigItem[] = [
  { id: "chat", label: "Chat", icon: MessageSquare, to: "/chat" },
  { id: "documents", label: "Documents", icon: FileText, to: "/documents" },
  { id: "memory", label: "Memory", icon: Brain, to: "/memory" },
  { id: "wiki", label: "Wiki", icon: BookOpen, to: "/wiki" },
  { id: "vaults", label: "Vaults", icon: Database, to: "/vaults" },
  { id: "settings", label: "Settings", icon: Settings, to: "/settings" },
  { id: "groups", label: "Groups", icon: Users, to: "/admin/groups", adminOnly: true },
  { id: "users", label: "Users", icon: UserCog, to: "/admin/users", adminOnly: true },
  { id: "organizations", label: "Orgs", icon: Building2, to: "/admin/organizations", adminOnly: true },
  { id: "profile", label: "Profile", icon: UserCircle, to: "/profile" },
];

function StatusIndicator({ isUp, label, loading }: { isUp: boolean; label: string; loading?: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      <div
        className={cn(
          "w-2 h-2 rounded-full",
          loading ? "bg-warning animate-pulse" : isUp ? "bg-success" : "bg-destructive"
        )}
      />
      <span className="text-xs text-muted-foreground truncate">
        {loading ? "Checking" : label}
      </span>
      <span className="sr-only">{label}: {isUp ? "online" : "offline"}</span>
    </div>
  );
}

interface NavigationRailProps {
  healthStatus: NavigationProps["healthStatus"];
}

export function NavigationRail({ healthStatus }: NavigationRailProps) {
  const location = useLocation();
  const pathname = location.pathname;
  const { theme, setTheme } = useThemeStore();
  const userRole = useAuthStore((state) => state.user?.role);
  const isAdmin = userRole === "admin" || userRole === "superadmin";

  // Determine active item based on current pathname
  const getActiveItem = (): NavItemId | null => {
    // Check exact matches first
    for (const item of navItems) {
      if (item.to === pathname) {
        return item.id;
      }
    }
    // Check partial matches for nested routes
    if (pathname.startsWith("/chat/")) return "chat";
    if (pathname.startsWith("/admin/groups")) return "groups";
    if (pathname.startsWith("/admin/users")) return "users";
    if (pathname.startsWith("/admin/organizations")) return "organizations";
    if (pathname.startsWith("/profile")) return "profile";
    return null;
  };

  const activeItem = getActiveItem();

  return (
    <nav className="w-20 min-h-screen bg-card border-r border-border flex flex-col items-center py-6 gap-2" aria-label="Main navigation">
      {/* App Logo */}
      <div className="mb-8 mx-auto w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
        <span className="text-primary-foreground font-bold text-sm">KV</span>
      </div>

      {/* Navigation Items */}
      <div className="flex flex-col gap-1 w-full px-2">
        {navItems.filter((item) => !item.adminOnly || isAdmin).map((item) => {
          const Icon = item.icon;
          const isActive = activeItem === item.id;

          return (
            <NavLink
              key={item.id}
              to={item.to}
              className={cn(
                "group relative flex flex-col items-center gap-1 p-3 rounded-xl transition-all duration-200 ease-out",
                "hover:bg-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                isActive && "bg-primary/10"
              )}
              aria-label={item.label}
              aria-current={isActive ? "page" : undefined}
            >
              {/* Icon Container */}
              <div
                className={cn(
                  "relative p-2 rounded-lg transition-all duration-200",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground group-hover:text-foreground"
                )}
              >
                <Icon className="w-5 h-5" />
              </div>

              {/* Label */}
              <span
                className={cn(
                  "text-xs font-medium transition-colors duration-200",
                  isActive
                    ? "text-primary"
                    : "text-muted-foreground group-hover:text-foreground"
                )}
              >
                {item.label}
              </span>

              {/* Tooltip for larger screens */}
              <span className="sr-only">{item.label}</span>
            </NavLink>
          );
        })}
      </div>

      {/* Bottom Spacer */}
      <div className="mt-auto" />

      {/* Theme Toggle (H-30) */}
      <button
        type="button"
        onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        className="p-2 rounded-lg hover:bg-secondary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      >
        {theme === "dark" ? (
          <Sun className="w-4 h-4 text-muted-foreground" />
        ) : (
          <Moon className="w-4 h-4 text-muted-foreground" />
        )}
      </button>

      {/* Health Status Footer */}
      <div className="w-full px-2 pb-4">
        <div className="flex flex-col gap-1.5 p-2 rounded-lg bg-muted/50">
          <StatusIndicator isUp={healthStatus.backend} label="API" loading={healthStatus.loading} />
          <StatusIndicator isUp={healthStatus.embeddings} label="Embeddings" loading={healthStatus.loading} />
          <StatusIndicator isUp={healthStatus.chat} label="Chat" loading={healthStatus.loading} />
        </div>
      </div>
    </nav>
  );
}

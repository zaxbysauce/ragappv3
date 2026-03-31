import { MessageSquare, FileText, Brain, Settings, Database, Sparkles, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import type { NavItem, NavItemId, NavigationProps } from "./navigationTypes";

// Re-export types for backward compatibility
export type { NavItemId, NavigationProps };

const navItems: NavItem[] = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "chatNew", label: "Chat (New)", icon: Sparkles },
  { id: "documents", label: "Documents", icon: FileText },
  { id: "memory", label: "Memory", icon: Brain },
  { id: "vaults", label: "Vaults", icon: Database },
  { id: "settings", label: "Settings", icon: Settings },
  { id: "groups", label: "Groups", icon: Users },
];

interface NavigationRailProps extends Omit<NavigationProps, 'onItemSelect'> {
  onItemSelect: (id: NavItemId) => void;
}

function StatusIndicator({ isUp, label, loading }: { isUp: boolean; label: string; loading?: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      <div
        className={cn(
          "w-2 h-2 rounded-full",
          loading ? "bg-yellow-500 animate-pulse" : isUp ? "bg-green-500" : "bg-red-500"
        )}
      />
      <span className="text-[9px] text-muted-foreground truncate">
        {loading ? "Checking" : label}
      </span>
    </div>
  );
}

export function NavigationRail({ activeItem, onItemSelect, healthStatus }: NavigationRailProps) {
  return (
    <nav className="w-20 min-h-screen bg-card/80 backdrop-blur-sm border-r border-border flex flex-col items-center py-6 gap-2" aria-label="Main navigation">
      {/* App Logo */}
      <div className="mb-8 p-3 rounded-xl bg-primary/10">
        <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
          <span className="text-primary-foreground font-bold text-sm">KV</span>
        </div>
      </div>

      {/* Navigation Items */}
      <div className="flex flex-col gap-1 w-full px-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeItem === item.id;
          const isNewChat = item.id === "chatNew";
          const isGroups = item.id === "groups";

          return (
            <button
              key={item.id}
              onClick={isNewChat ? () => window.location.href = "/chat/redesign" : isGroups ? () => window.location.href = "/admin/groups" : () => onItemSelect(item.id)}
              className={cn(
                "group relative flex flex-col items-center gap-1 p-3 rounded-xl transition-all duration-200 ease-out",
                "hover:bg-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                isActive && "bg-primary/10",
                isNewChat && "bg-gradient-to-br from-purple-500/10 to-pink-500/10 hover:from-purple-500/20 hover:to-pink-500/20 border border-purple-500/30"
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
                    : "text-muted-foreground group-hover:text-foreground",
                  isNewChat && "bg-gradient-to-br from-purple-500 to-pink-500 text-white shadow-lg shadow-purple-500/25"
                )}
              >
                <Icon className={cn("w-5 h-5", isNewChat && "animate-pulse")} />

                {/* Active Indicator */}
                {isActive && !isNewChat && (
                  <span className="absolute -right-1 top-1/2 -translate-y-1/2 w-1 h-4 bg-primary rounded-full" />
                )}

                {/* New Badge */}
                {isNewChat && (
                  <span className="absolute -top-1 -right-1 px-1.5 py-0.5 text-[8px] font-bold bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-full shadow-md">
                    NEW
                  </span>
                )}
              </div>

              {/* Label */}
              <span
                className={cn(
                  "text-[10px] font-medium transition-colors duration-200",
                  isActive
                    ? "text-primary"
                    : "text-muted-foreground group-hover:text-foreground",
                  isNewChat && "font-bold bg-gradient-to-r from-purple-500 to-pink-500 bg-clip-text text-transparent"
                )}
              >
                {item.label}
              </span>

              {/* Tooltip for larger screens */}
              <span className="sr-only">{item.label}</span>
            </button>
          );
        })}
      </div>

      {/* Bottom Spacer */}
      <div className="mt-auto" />

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

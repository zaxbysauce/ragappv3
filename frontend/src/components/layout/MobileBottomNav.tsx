import { useState } from "react";
import { MessageSquare, FileText, Brain, MoreHorizontal, Database, Settings, Users, UserCircle, X } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import type { NavItemId } from "./navigationTypes";

interface MobileBottomNavProps {
  activeItem: NavItemId;
  onItemSelect: (id: NavItemId) => void;
}

// Primary tabs shown on bottom nav
const primaryNavItems = [
  { id: "chat" as const, label: "Chat", icon: MessageSquare },
  { id: "documents" as const, label: "Documents", icon: FileText },
  { id: "memory" as const, label: "Memory", icon: Brain },
];

// Secondary items shown in "More" drawer
const moreNavItems = [
  { id: "vaults" as const, label: "Vaults", icon: Database },
  { id: "settings" as const, label: "Settings", icon: Settings },
  { id: "groups" as const, label: "Groups", icon: UserCircle },
  { id: "users" as const, label: "Users", icon: Users },
];

export function MobileBottomNav({ activeItem, onItemSelect }: MobileBottomNavProps) {
  const [moreOpen, setMoreOpen] = useState(false);

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-card/95 backdrop-blur-sm border-t border-border z-50 md:hidden" aria-label="Mobile navigation">
      <div className="flex items-center justify-around px-2 py-2" style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}>
        {/* Primary Tabs */}
        {primaryNavItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeItem === item.id;

          return (
            <button
              key={item.id}
              onClick={() => onItemSelect(item.id)}
              className={cn(
                "flex flex-col items-center gap-1 min-w-[44px] min-h-[44px] px-3 py-2 rounded-lg transition-all duration-200",
                "hover:bg-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                isActive && "bg-primary/10"
              )}
              aria-label={item.label}
              aria-current={isActive ? "page" : undefined}
            >
              <Icon
                className={cn(
                  "w-5 h-5 transition-colors",
                  isActive ? "text-primary" : "text-muted-foreground"
                )}
              />
              <span
                className={cn(
                  "text-[10px] font-medium transition-colors",
                  isActive ? "text-primary" : "text-muted-foreground"
                )}
              >
                {item.label}
              </span>
            </button>
          );
        })}

        {/* More Button with Sheet */}
        <Sheet open={moreOpen} onOpenChange={setMoreOpen}>
          <SheetTrigger asChild>
            <button
              className={cn(
                "flex flex-col items-center gap-1 min-w-[44px] min-h-[44px] px-3 py-2 rounded-lg transition-all duration-200",
                "hover:bg-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                moreOpen && "bg-primary/10"
              )}
              aria-label="More options"
              aria-expanded={moreOpen}
            >
              <MoreHorizontal
                className={cn(
                  "w-5 h-5 transition-colors",
                  moreOpen ? "text-primary" : "text-muted-foreground"
                )}
              />
              <span
                className={cn(
                  "text-[10px] font-medium transition-colors",
                  moreOpen ? "text-primary" : "text-muted-foreground"
                )}
              >
                More
              </span>
            </button>
          </SheetTrigger>
          <SheetContent side="bottom" className="h-[50vh] rounded-t-2xl">
            <SheetHeader className="mb-6">
              <div className="flex items-center justify-between">
                <SheetTitle className="text-xl font-semibold">More</SheetTitle>
                <button
                  onClick={() => setMoreOpen(false)}
                  className="p-2 rounded-lg hover:bg-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-ring min-w-[44px] min-h-[44px]"
                  aria-label="Close"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </SheetHeader>

            <div className="grid grid-cols-2 gap-3">
              {moreNavItems.map((item) => {
                const Icon = item.icon;
                const isActive = activeItem === item.id;

                return (
                  <button
                    key={item.id}
                    onClick={() => {
                      onItemSelect(item.id);
                      setMoreOpen(false);
                    }}
                    className={cn(
                      "flex flex-col items-center gap-3 p-4 rounded-xl border border-border transition-all duration-200",
                      "hover:bg-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      isActive && "bg-primary/10 border-primary/20"
                    )}
                    aria-label={item.label}
                  >
                    <Icon
                      className={cn(
                        "w-6 h-6 transition-colors",
                        isActive ? "text-primary" : "text-muted-foreground"
                      )}
                    />
                    <span
                      className={cn(
                        "text-sm font-medium transition-colors",
                        isActive ? "text-primary" : "text-foreground"
                      )}
                    >
                      {item.label}
                    </span>
                  </button>
                );
              })}
            </div>
          </SheetContent>
        </Sheet>
      </div>
    </nav>
  );
}

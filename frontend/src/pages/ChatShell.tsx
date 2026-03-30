import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useChatShellStore } from "@/stores/useChatShellStore";
import { SessionRail } from "@/components/chat/SessionRail";
import { TranscriptPane } from "@/components/chat/TranscriptPane";
import { RightPane } from "@/components/chat/RightPane";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetClose,
} from "@/components/ui/sheet";
import { PanelLeft, PanelRight, X } from "lucide-react";

export default function ChatShell() {
  const { sessionId } = useParams<{ sessionId?: string }>();
  const {
    sessionRailOpen,
    rightPaneOpen,
    rightPaneWidth,
    activeSessionId,
    activeRightTab,
    toggleSessionRail,
    toggleRightPane,
    setRightPaneWidth,
    setActiveSessionId,
    closeSessionRail,
    closeRightPane,
  } = useChatShellStore();

  useEffect(() => {
    if (sessionId && sessionId !== activeSessionId) {
      setActiveSessionId(sessionId);
    } else if (!sessionId && activeSessionId) {
      setActiveSessionId(null);
    }
  }, [sessionId, activeSessionId, setActiveSessionId]);

  const handleResizeStart = (e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = rightPaneWidth;
    const onMouseMove = (moveEvent: MouseEvent) => {
      const delta = startX - moveEvent.clientX;
      const newWidth = Math.max(240, Math.min(600, startWidth + delta));
      setRightPaneWidth(newWidth);
    };
    const onMouseUp = () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
      window.removeEventListener("blur", onMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
    window.addEventListener("blur", onMouseUp);
  };

  // Determine if workspace tab should open full-screen on mobile
  const isWorkspaceFullScreen = activeRightTab === "workspace" && rightPaneOpen;

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* DESKTOP: Session Rail (persistent sidebar) */}
      <aside
        className={cn(
          "hidden md:flex md:flex-col md:flex-shrink-0 md:border-r md:border-border md:bg-background md:transition-all md:duration-300 md:ease-in-out",
          "w-[240px]",
          sessionRailOpen ? "md:translate-x-0 md:opacity-100" : "md:w-0 md:opacity-0 md:overflow-hidden"
        )}
        aria-label="Chat sessions"
      >
        <SessionRail />
      </aside>

      {/* MOBILE: Session Rail Sheet (slides from left) */}
      <Sheet open={sessionRailOpen} onOpenChange={(open) => !open && closeSessionRail()}>
        <SheetContent side="left" className="w-[280px] p-0 md:hidden">
          <SheetHeader className="sr-only">
            <SheetTitle>Chat Sessions</SheetTitle>
          </SheetHeader>
          <div className="flex h-full flex-col">
            <SessionRail />
          </div>
        </SheetContent>
      </Sheet>

      {/* MAIN TRANSCRIPT AREA */}
      <main className="flex flex-1 flex-col min-w-0 bg-background">
        <header className="flex h-14 items-center justify-between border-b border-border px-4">
          {/* Session rail toggle — mobile only */}
          <Button variant="ghost" size="icon" onClick={toggleSessionRail}
            aria-label={sessionRailOpen ? "Hide sessions" : "Show sessions"}
            aria-pressed={sessionRailOpen} className="md:hidden">
            <PanelLeft className="h-5 w-5" aria-hidden="true" />
          </Button>
          <div className="flex-1" />
          <Button variant="ghost" size="icon" onClick={toggleRightPane}
            aria-label={rightPaneOpen ? "Hide details panel" : "Show details panel"}
            aria-pressed={rightPaneOpen}>
            <PanelRight className="h-5 w-5" aria-hidden="true" />
          </Button>
        </header>
        <div className="flex-1 overflow-hidden">
          <TranscriptPane />
        </div>
        {/* MOBILE: Safe area padding for iOS */}
        <div className="md:hidden" style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }} aria-hidden="true" />
      </main>

      {/* DESKTOP: Right Pane (persistent resizable sidebar) */}
      <aside
        className={cn(
          "hidden lg:flex lg:flex-col lg:flex-shrink-0 lg:border-l lg:border-border lg:bg-background lg:transition-all lg:duration-300 lg:ease-in-out",
          rightPaneOpen ? "lg:translate-x-0 lg:opacity-100" : "lg:w-0 lg:opacity-0 lg:overflow-hidden"
        )}
        style={{ width: rightPaneOpen ? `${rightPaneWidth}px` : undefined }}
        aria-label="Details panel"
      >
        {rightPaneOpen && (
          <div className="relative left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-primary/20 active:bg-primary/40 transition-colors hidden lg:block" onMouseDown={handleResizeStart} role="separator" aria-label="Resize details panel" aria-orientation="vertical" />
        )}
        <div className="flex h-full flex-col p-4">
          <RightPane />
        </div>
      </aside>

      {/* MOBILE: Right Pane Sheet (slides from bottom, 75vh) */}
      {!isWorkspaceFullScreen && (
        <Sheet open={rightPaneOpen} onOpenChange={(open) => !open && closeRightPane()}>
          <SheetContent side="bottom" className="h-[75vh] rounded-t-xl p-0 lg:hidden">
            <SheetHeader className="sr-only">
              <SheetTitle>Evidence & Sources</SheetTitle>
            </SheetHeader>
            <div className="absolute right-4 top-4 z-10">
              <SheetClose asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Close details panel">
                  <X className="h-4 w-4" aria-hidden="true" />
                </Button>
              </SheetClose>
            </div>
            <div className="flex h-full flex-col p-4 pt-12">
              <RightPane />
            </div>
          </SheetContent>
        </Sheet>
      )}

      {/* MOBILE: Workspace Full-Screen Sheet */}
      {isWorkspaceFullScreen && (
        <Sheet open={rightPaneOpen} onOpenChange={(open) => !open && closeRightPane()}>
          <SheetContent side="bottom" className="h-[95vh] rounded-t-xl p-0 lg:hidden">
            <SheetHeader className="sr-only">
              <SheetTitle>Workspace</SheetTitle>
            </SheetHeader>
            <div className="absolute right-4 top-4 z-10">
              <SheetClose asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Close workspace">
                  <X className="h-4 w-4" aria-hidden="true" />
                </Button>
              </SheetClose>
            </div>
            <div className="flex h-full flex-col p-4 pt-12">
              <RightPane />
            </div>
          </SheetContent>
        </Sheet>
      )}
    </div>
  );
}

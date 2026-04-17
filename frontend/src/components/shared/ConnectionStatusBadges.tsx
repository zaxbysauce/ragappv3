import { Badge } from "@/components/ui/badge";
import { Server, Cpu, MessageCircle } from "lucide-react";
import type { HealthStatus } from "@/types/health";

export function ConnectionStatusBadges({ health }: { health: HealthStatus }) {
  const getBadgeClass = (isUp: boolean) => {
    if (health.loading) return "bg-muted text-muted-foreground";
    return isUp ? "bg-success hover:bg-success/80" : "bg-destructive hover:bg-destructive/80";
  };

  const getBadgeLabel = (label: string) => {
    return health.loading ? "Checking" : label;
  };

  return (
    <div className="flex items-center gap-2">
      <Badge variant="default" className={getBadgeClass(health.backend)}>
        <Server className="w-3 h-3 mr-1" />
        {getBadgeLabel("Backend")}
      </Badge>
      <Badge variant="default" className={getBadgeClass(health.embeddings)}>
        <Cpu className="w-3 h-3 mr-1" />
        {getBadgeLabel("Embeddings")}
      </Badge>
      <Badge variant="default" className={getBadgeClass(health.chat)}>
        <MessageCircle className="w-3 h-3 mr-1" />
        {getBadgeLabel("Chat")}
      </Badge>
    </div>
  );
}

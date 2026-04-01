import { useEffect } from "react";
import { Database, ChevronDown, Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useVaultStore } from "@/stores/useVaultStore";
import { cn } from "@/lib/utils";

interface VaultSelectorProps {
  className?: string;
}

export function VaultSelector({ className }: VaultSelectorProps) {
  const { vaults, activeVaultId, setActiveVault, fetchVaults, getActiveVault } = useVaultStore();
  const activeVault = getActiveVault();

  useEffect(() => {
    if (!vaults || vaults.length === 0) {
      fetchVaults();
    }
  }, [vaults?.length, fetchVaults]);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className={cn("gap-2", className)}>
          <Database className="h-4 w-4" />
          <span className="truncate max-w-[150px]">{activeVault?.name ?? "All Vaults"}</span>
          <ChevronDown className="h-3 w-3 opacity-50" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <DropdownMenuLabel>Select Vault</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={() => setActiveVault(null)}
          className={cn(activeVaultId === null && "font-semibold bg-accent")}
        >
          <Globe className="mr-2 h-4 w-4" />
          All Vaults
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {vaults?.map((vault) => (
          <DropdownMenuItem
            key={vault.id}
            onClick={() => setActiveVault(vault.id)}
            className={cn(vault.id === activeVaultId && "font-semibold bg-accent")}
          >
            <Database className="mr-2 h-4 w-4" />
            <div className="flex flex-col">
              <span>{vault.name}</span>
              <span className="text-xs text-muted-foreground">{vault.file_count} files</span>
            </div>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

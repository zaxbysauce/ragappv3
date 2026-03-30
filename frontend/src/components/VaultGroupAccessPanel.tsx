import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import apiClient from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Users, UserX, Loader2, Building2 } from "lucide-react";

type VaultPermission = "read" | "write" | "admin";

interface GroupAccess {
  group_id: number;
  group_name: string;
  org_name: string;
  permission: VaultPermission;
  granted_at: string;
  granted_by: string;
}

const PERMISSION_OPTIONS: { value: VaultPermission; label: string }[] = [
  { value: "read", label: "Read" },
  { value: "write", label: "Write" },
  { value: "admin", label: "Admin" },
];

interface VaultGroupAccessPanelProps {
  vaultId: number;
}

export function VaultGroupAccessPanel({ vaultId }: VaultGroupAccessPanelProps) {
  const [groupAccessList, setGroupAccessList] = useState<GroupAccess[]>([]);
  const [loading, setLoading] = useState(true);
  const [addingGroup, setAddingGroup] = useState(false);
  const [newGroupId, setNewGroupId] = useState("");
  const [newGroupPermission, setNewGroupPermission] = useState<VaultPermission>("read");
  const [removeDialogOpen, setRemoveDialogOpen] = useState(false);
  const [groupToRemove, setGroupToRemove] = useState<GroupAccess | null>(null);
  const [updatingGroupId, setUpdatingGroupId] = useState<number | null>(null);

  const fetchGroupAccess = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiClient.get<{ group_access: GroupAccess[]; total: number }>(
        `/vaults/${vaultId}/group-access`
      );
      setGroupAccessList(response.data.group_access ?? []);
    } catch (err) {
      console.error("Failed to fetch group access:", err);
      toast.error("Failed to load group access");
    } finally {
      setLoading(false);
    }
  }, [vaultId]);

  useEffect(() => { fetchGroupAccess(); }, [fetchGroupAccess]);

  const handleAddGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newGroupId.trim()) return;
    const groupId = parseInt(newGroupId, 10);
    if (isNaN(groupId)) { toast.error("Please enter a valid group ID"); return; }
    setAddingGroup(true);
    try {
      await apiClient.post(`/vaults/${vaultId}/group-access`, { group_id: groupId, permission: newGroupPermission });
      toast.success("Group access granted");
      setNewGroupId("");
      setNewGroupPermission("read");
      fetchGroupAccess();
    } catch (err) { toast.error("Failed to grant group access"); }
    finally { setAddingGroup(false); }
  };

  const handlePermissionChange = async (groupId: number, newPermission: VaultPermission) => {
    setUpdatingGroupId(groupId);
    try {
      await apiClient.patch(`/vaults/${vaultId}/group-access/${groupId}`, { permission: newPermission });
      setGroupAccessList((prev) => prev.map((g) => (g.group_id === groupId ? { ...g, permission: newPermission } : g)));
      toast.success("Permission updated");
    } catch (err) { toast.error("Failed to update permission"); }
    finally { setUpdatingGroupId(null); }
  };

  const handleRemove = async () => {
    if (!groupToRemove) return;
    try {
      await apiClient.delete(`/vaults/${vaultId}/group-access/${groupToRemove.group_id}`);
      setGroupAccessList((prev) => prev.filter((g) => g.group_id !== groupToRemove.group_id));
      toast.success("Group access revoked");
      setRemoveDialogOpen(false);
      setGroupToRemove(null);
    } catch (err) { toast.error("Failed to revoke group access"); }
  };

  const formatDate = (dateStr: string) => new Date(dateStr).toLocaleDateString();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Building2 className="w-5 h-5" />Group Access</CardTitle>
        <CardDescription>Manage organization group access to this vault</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <form onSubmit={handleAddGroup} className="flex gap-2 items-end">
          <div className="flex-1 space-y-2">
            <label htmlFor={`group-id-${vaultId}`} className="text-sm font-medium">Group ID</label>
            <Input id={`group-id-${vaultId}`} placeholder="Enter group ID..." value={newGroupId} onChange={(e) => setNewGroupId(e.target.value)} disabled={addingGroup} aria-label="Group ID to grant vault access" />
          </div>
          <div className="space-y-2">
            <label htmlFor={`group-perm-${vaultId}`} className="text-sm font-medium">Permission</label>
            <select id={`group-perm-${vaultId}`} value={newGroupPermission} onChange={(e) => setNewGroupPermission(e.target.value as VaultPermission)} disabled={addingGroup} aria-label="Permission level for group access" className="h-10 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring">
              {PERMISSION_OPTIONS.map((opt) => (<option key={opt.value} value={opt.value}>{opt.label}</option>))}
            </select>
          </div>
          <Button type="submit" disabled={addingGroup || !newGroupId.trim()}>
            {addingGroup ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Users className="w-4 h-4 mr-2" />}
            Grant
          </Button>
        </form>
        <div className="overflow-x-auto">
          <table className="w-full">
            <caption className="sr-only">Group Access List</caption>
            <thead>
              <tr className="border-b">
                <th scope="col" className="text-left py-2 font-medium">Group</th>
                <th scope="col" className="text-left py-2 font-medium">Organization</th>
                <th scope="col" className="text-left py-2 font-medium">Permission</th>
                <th scope="col" className="text-left py-2 font-medium">Granted</th>
                <th scope="col" className="text-right py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} className="py-8 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" role="status" aria-live="polite" /><span className="sr-only">Loading group access</span></td></tr>
              ) : groupAccessList.length === 0 ? (
                <tr><td colSpan={5} className="py-8 text-center text-muted-foreground" role="status" aria-live="polite">No groups have access yet. Grant access to organization groups to give their members vault permissions.</td></tr>
              ) : (
                groupAccessList.map((group) => (
                  <tr key={group.group_id} className="border-b last:border-0">
                    <td className="py-3"><div className="font-medium">{group.group_name}</div></td>
                    <td className="py-3 text-muted-foreground text-sm">{group.org_name}</td>
                    <td className="py-3">
                      <select value={group.permission} onChange={(e) => handlePermissionChange(group.group_id, e.target.value as VaultPermission)} disabled={updatingGroupId === group.group_id} aria-label={`Change permission for ${group.group_name}`} className="h-8 rounded-md border border-input bg-background px-2 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50">
                        {PERMISSION_OPTIONS.map((opt) => (<option key={opt.value} value={opt.value}>{opt.label}</option>))}
                      </select>
                    </td>
                    <td className="py-3 text-muted-foreground text-sm">{formatDate(group.granted_at)}</td>
                    <td className="py-3 text-right">
                      <Button variant="ghost" size="icon" onClick={() => { setGroupToRemove(group); setRemoveDialogOpen(true); }} aria-label={`Revoke access for ${group.group_name}`} className="text-destructive hover:text-destructive hover:bg-destructive/10"><UserX className="w-4 h-4" /></Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
      <Dialog open={removeDialogOpen} onOpenChange={setRemoveDialogOpen}>
        <DialogContent aria-labelledby="revoke-group-title" aria-describedby="revoke-group-desc">
          <DialogHeader>
            <DialogTitle id="revoke-group-title" className="flex items-center gap-2"><UserX className="w-5 h-5 text-destructive" />Revoke Group Access</DialogTitle>
            <DialogDescription id="revoke-group-desc">Are you sure you want to revoke vault access for <strong>{groupToRemove?.group_name}</strong> ({groupToRemove?.org_name})?</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRemoveDialogOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleRemove}>Revoke</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

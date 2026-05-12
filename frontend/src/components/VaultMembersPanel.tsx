import { useState, useEffect, useCallback, useRef } from "react";
import { toast } from "sonner";
import apiClient from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { UserPlus, UserX, Loader2, Users, Search } from "lucide-react";

type VaultPermission = "read" | "write" | "admin";

interface VaultMember {
  user_id: number;
  username: string;
  full_name: string;
  permission: VaultPermission;
  granted_at: string;
}

const PERMISSION_OPTIONS: { value: VaultPermission; label: string }[] = [
  { value: "read", label: "Read" },
  { value: "write", label: "Write" },
  { value: "admin", label: "Admin" },
];

interface VaultMembersPanelProps {
  vaultId: number;
}

export function VaultMembersPanel({ vaultId }: VaultMembersPanelProps) {
  const [members, setMembers] = useState<VaultMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [addingMember, setAddingMember] = useState(false);
  const [newMemberUserId, setNewMemberUserId] = useState("");
  const [newMemberPermission, setNewMemberPermission] = useState<VaultPermission>("read");
  const [removeDialogOpen, setRemoveDialogOpen] = useState(false);
  const [memberToRemove, setMemberToRemove] = useState<VaultMember | null>(null);
  const [updatingMemberId, setUpdatingMemberId] = useState<number | null>(null);
  const [userSearchQuery, setUserSearchQuery] = useState("");
  const [userSearchResults, setUserSearchResults] = useState<{id: number; username: string; full_name: string}[]>([]);
  const [showUserDropdown, setShowUserDropdown] = useState(false);
  const [searchingUsers, setSearchingUsers] = useState(false);
  const userSearchRef = useRef<HTMLDivElement>(null);
  const userSearchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchMembers = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiClient.get<{ members: VaultMember[]; total: number }>(`/vaults/${vaultId}/members`);
      setMembers(response.data.members);
    } catch (err) {
      console.error("Failed to fetch members:", err);
      toast.error("Failed to load vault members");
    } finally { setLoading(false); }
  }, [vaultId]);

  useEffect(() => { fetchMembers(); }, [fetchMembers]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (userSearchRef.current && !userSearchRef.current.contains(e.target as Node)) {
        setShowUserDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    return () => {
      if (userSearchTimeoutRef.current) clearTimeout(userSearchTimeoutRef.current);
    };
  }, []);

  const searchUsers = useCallback(async (query: string) => {
    if (!query.trim()) {
      setUserSearchResults([]);
      setShowUserDropdown(false);
      return;
    }
    setSearchingUsers(true);
    try {
      const response = await apiClient.get<{ users: {id: number; username: string; full_name: string}[] }>("/users/", { params: { q: query, limit: 10 } });
      const users = Array.isArray(response.data) ? response.data : response.data.users ?? [];
      setUserSearchResults(users.filter((u: any) => u.is_active !== false));
      setShowUserDropdown(true);
    } catch {
      setUserSearchResults([]);
    } finally {
      setSearchingUsers(false);
    }
  }, []);

  const handleUserSearchChange = (value: string) => {
    setUserSearchQuery(value);
    if (userSearchTimeoutRef.current) clearTimeout(userSearchTimeoutRef.current);
    userSearchTimeoutRef.current = setTimeout(() => searchUsers(value), 300);
  };

  const selectUser = (user: {id: number; username: string; full_name: string}) => {
    setUserSearchQuery(`${user.full_name || user.username} (${user.username})`);
    setNewMemberUserId(String(user.id));
    setShowUserDropdown(false);
  };

  const handleAddMember = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMemberUserId.trim()) return;
    const userId = parseInt(newMemberUserId, 10);
    if (isNaN(userId)) { toast.error("Please enter a valid user ID"); return; }
    setAddingMember(true);
    try {
      await apiClient.post(`/vaults/${vaultId}/members`, { member_user_id: userId, permission: newMemberPermission });
      toast.success("Member added to vault");
      setNewMemberUserId("");
      setNewMemberPermission("read");
      fetchMembers();
    } catch (err) { toast.error("Failed to add member"); }
    finally { setAddingMember(false); }
  };

  const handlePermissionChange = async (userId: number, newPermission: VaultPermission) => {
    setUpdatingMemberId(userId);
    try {
      await apiClient.patch(`/vaults/${vaultId}/members/${userId}`, { permission: newPermission });
      setMembers((prev) => prev.map((m) => (m.user_id === userId ? { ...m, permission: newPermission } : m)));
      toast.success("Permission updated");
    } catch (err) { toast.error("Failed to update permission"); }
    finally { setUpdatingMemberId(null); }
  };

  const handleRemove = async () => {
    if (!memberToRemove) return;
    try {
      await apiClient.delete(`/vaults/${vaultId}/members/${memberToRemove.user_id}`);
      setMembers((prev) => prev.filter((m) => m.user_id !== memberToRemove.user_id));
      toast.success("Member removed from vault");
      setRemoveDialogOpen(false);
      setMemberToRemove(null);
    } catch (err) { toast.error("Failed to remove member"); }
  };

  const formatDate = (dateStr: string) => new Date(dateStr).toLocaleDateString();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Users className="w-5 h-5" />Vault Members</CardTitle>
        <CardDescription>Manage who has access to this vault</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <form onSubmit={handleAddMember} className="flex gap-2 items-end">
          <div className="flex-1 space-y-2 relative" ref={userSearchRef}>
            <label htmlFor={`member-userid-${vaultId}`} className="text-sm font-medium">User</label>
            <div className="relative">
              <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                id={`member-userid-${vaultId}`}
                placeholder="Search users..."
                value={userSearchQuery}
                onChange={(e) => handleUserSearchChange(e.target.value)}
                onFocus={() => { if (userSearchResults.length > 0) setShowUserDropdown(true); }}
                className="pl-8"
                aria-label="Search users"
              />
            </div>
            {showUserDropdown && userSearchResults.length > 0 && (
              <div className="absolute z-50 w-full mt-1 rounded-md border bg-popover shadow-md max-h-60 overflow-auto">
                {userSearchResults.map((u) => (
                  <button
                    key={u.id}
                    type="button"
                    onClick={() => selectUser(u)}
                    className="w-full px-3 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground transition-colors flex flex-col"
                  >
                    <span>{u.full_name || u.username}</span>
                    <span className="text-xs text-muted-foreground">@{u.username}</span>
                  </button>
                ))}
              </div>
            )}
            {showUserDropdown && userSearchQuery.trim() && !searchingUsers && userSearchResults.length === 0 && (
              <div className="absolute z-50 w-full mt-1 rounded-md border bg-popover p-2 text-sm text-muted-foreground text-center">
                No users found
              </div>
            )}
            {searchingUsers && (
              <div className="absolute z-50 w-full mt-1 rounded-md border bg-popover p-2 text-sm text-muted-foreground text-center">
                Searching...
              </div>
            )}
          </div>
          <div className="space-y-2">
            <label htmlFor={`member-perm-${vaultId}`} className="text-sm font-medium">Permission</label>
            <select id={`member-perm-${vaultId}`} value={newMemberPermission} onChange={(e) => setNewMemberPermission(e.target.value as VaultPermission)} disabled={addingMember} aria-label="Permission level for new member" className="h-10 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring">
              {PERMISSION_OPTIONS.map((opt) => (<option key={opt.value} value={opt.value}>{opt.label}</option>))}
            </select>
          </div>
          <Button type="submit" disabled={addingMember || !newMemberUserId.trim()}>
            {addingMember ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <UserPlus className="w-4 h-4 mr-2" />}
            Add
          </Button>
        </form>
        <div className="overflow-x-auto">
          <table className="w-full">
            <caption className="sr-only">Vault Members</caption>
            <thead>
              <tr className="border-b">
                <th scope="col" className="text-left py-2 font-medium">User</th>
                <th scope="col" className="text-left py-2 font-medium">Permission</th>
                <th scope="col" className="text-left py-2 font-medium">Added</th>
                <th scope="col" className="text-right py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={4} className="py-8 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" role="status" aria-live="polite" /><span className="sr-only">Loading members</span></td></tr>
              ) : members.length === 0 ? (
                <tr><td colSpan={4} className="py-8 text-center text-muted-foreground" role="status" aria-live="polite">No members yet. Add users to give them access to this vault.</td></tr>
              ) : (
                members.map((member) => (
                  <tr key={member.user_id} className="border-b last:border-0">
                    <td className="py-3"><div><div className="font-medium">{member.full_name || member.username}</div><div className="text-sm text-muted-foreground">@{member.username}</div></div></td>
                    <td className="py-3">
                      <select value={member.permission} onChange={(e) => handlePermissionChange(member.user_id, e.target.value as VaultPermission)} disabled={updatingMemberId === member.user_id} aria-label={`Change permission for ${member.username}`} className="h-8 rounded-md border border-input bg-background px-2 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50">
                        {PERMISSION_OPTIONS.map((opt) => (<option key={opt.value} value={opt.value}>{opt.label}</option>))}
                      </select>
                    </td>
                    <td className="py-3 text-muted-foreground text-sm">{formatDate(member.granted_at)}</td>
                    <td className="py-3 text-right">
                      <Button variant="ghost" size="icon" onClick={() => { setMemberToRemove(member); setRemoveDialogOpen(true); }} aria-label={`Remove ${member.username} from vault`} className="text-destructive hover:text-destructive hover:bg-destructive/10"><UserX className="w-4 h-4" /></Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
      <Dialog open={removeDialogOpen} onOpenChange={setRemoveDialogOpen}>
        <DialogContent aria-labelledby="remove-member-title" aria-describedby="remove-member-desc">
          <DialogHeader>
            <DialogTitle id="remove-member-title" className="flex items-center gap-2"><UserX className="w-5 h-5 text-destructive" />Remove Member</DialogTitle>
            <DialogDescription id="remove-member-desc">Are you sure you want to remove <strong>{memberToRemove?.full_name || memberToRemove?.username}</strong> from this vault?</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRemoveDialogOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleRemove}>Remove</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { AdminGuard } from "@/components/auth/RoleGuard";
import { useAuthStore } from "@/stores/useAuthStore";
import apiClient from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Search, Trash2, Loader2, UserX } from "lucide-react";

type UserRole = "superadmin" | "admin" | "member" | "viewer";

interface User {
  id: number;
  username: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: "superadmin", label: "Super Admin" },
  { value: "admin", label: "Admin" },
  { value: "member", label: "Member" },
  { value: "viewer", label: "Viewer" },
];

function AdminUsersPageContent() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [updatingUserId, setUpdatingUserId] = useState<number | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [userToDelete, setUserToDelete] = useState<User | null>(null);
  const currentUser = useAuthStore((state) => state.user);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiClient.get<{ users: User[]; total: number }>("/users/");
      setUsers(response.data.users);
    } catch (err) {
      console.error("Failed to fetch users:", err);
      toast.error("Failed to load users");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const handleRoleChange = async (userId: number, newRole: UserRole) => {
    setUpdatingUserId(userId);
    try {
      await apiClient.patch(`/users/${userId}/role`, { role: newRole });
      setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, role: newRole } : u)));
      toast.success("Role updated successfully");
    } catch (err) { toast.error("Failed to update role"); }
    finally { setUpdatingUserId(null); }
  };

  const handleActiveToggle = async (userId: number, isActive: boolean) => {
    setUpdatingUserId(userId);
    try {
      await apiClient.patch(`/users/${userId}/active`, { is_active: isActive });
      setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, is_active: isActive } : u)));
      toast.success(`User ${isActive ? "activated" : "deactivated"} successfully`);
    } catch (err) { toast.error("Failed to update user status"); }
    finally { setUpdatingUserId(null); }
  };

  const handleDelete = async () => {
    if (!userToDelete) return;
    try {
      await apiClient.delete(`/users/${userToDelete.id}`);
      setUsers((prev) => prev.filter((u) => u.id !== userToDelete.id));
      toast.success("User deleted successfully");
      setDeleteDialogOpen(false);
      setUserToDelete(null);
    } catch (err) { toast.error("Failed to delete user"); }
  };

  const filteredUsers = (users ?? []).filter(
    (u) =>
      u.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
      u.full_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const formatDate = (dateStr: string) => new Date(dateStr).toLocaleDateString();
  const isSuperAdmin = currentUser?.role === "superadmin";
  const canDeleteUser = (user: User) => isSuperAdmin && user.id !== currentUser?.id;

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">User Management</h1>
        <p className="text-muted-foreground mt-1">Manage system users and their permissions</p>
      </div>
      <Card>
        <CardHeader className="pb-4">
          <div className="flex items-center gap-4">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input placeholder="Search by username or name..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="pl-10" aria-label="Search users" />
            </div>
            <Badge variant="secondary">{filteredUsers.length} users</Badge>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <caption className="sr-only">System Users</caption>
              <thead>
                <tr className="border-b bg-muted/50">
                  <th scope="col" className="text-left p-4 font-medium">Username</th>
                  <th scope="col" className="text-left p-4 font-medium">Full Name</th>
                  <th scope="col" className="text-left p-4 font-medium">Role</th>
                  <th scope="col" className="text-left p-4 font-medium">Status</th>
                  <th scope="col" className="text-left p-4 font-medium">Created</th>
                  <th scope="col" className="text-right p-4 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={6} className="p-8 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" role="status" aria-live="polite" /><span className="sr-only">Loading users</span></td></tr>
                ) : filteredUsers.length === 0 ? (
                  <tr><td colSpan={6} className="p-8 text-center text-muted-foreground" role="status" aria-live="polite">{searchQuery ? "No users match your search" : "No users found"}</td></tr>
                ) : (
                  filteredUsers.map((user) => (
                    <tr key={user.id} className="border-b hover:bg-muted/50">
                      <td className="p-4 font-medium">{user.username}</td>
                      <td className="p-4">{user.full_name}</td>
                      <td className="p-4">
                        <select value={user.role} onChange={(e) => handleRoleChange(user.id, e.target.value as UserRole)} disabled={updatingUserId === user.id || user.id === currentUser?.id} aria-label={`Change role for ${user.username}`} className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50">
                          {ROLE_OPTIONS.map((opt) => (<option key={opt.value} value={opt.value}>{opt.label}</option>))}
                        </select>
                      </td>
                      <td className="p-4">
                        <div className="flex items-center gap-2">
                          <button type="button" role="switch" aria-checked={user.is_active} aria-label={`${user.is_active ? "Deactivate" : "Activate"} user ${user.username}`} onClick={() => handleActiveToggle(user.id, !user.is_active)} disabled={updatingUserId === user.id || user.id === currentUser?.id} className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${user.is_active ? "bg-primary" : "bg-input"}`}>
                            <span className={`inline-block h-5 w-5 rounded-full bg-background shadow transition-transform ${user.is_active ? "translate-x-5" : "translate-x-0.5"}`} />
                          </button>
                          <Badge variant={user.is_active ? "default" : "secondary"}>{user.is_active ? "Active" : "Inactive"}</Badge>
                        </div>
                      </td>
                      <td className="p-4 text-muted-foreground">{formatDate(user.created_at)}</td>
                      <td className="p-4 text-right">
                        {canDeleteUser(user) && (
                          <Button variant="ghost" size="icon" onClick={() => { setUserToDelete(user); setDeleteDialogOpen(true); }} aria-label={`Delete user ${user.username}`} className="text-destructive hover:text-destructive hover:bg-destructive/10"><Trash2 className="w-4 h-4" /></Button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent aria-labelledby="delete-title" aria-describedby="delete-desc">
          <DialogHeader>
            <DialogTitle id="delete-title" className="flex items-center gap-2"><UserX className="w-5 h-5 text-destructive" />Delete User</DialogTitle>
            <DialogDescription id="delete-desc">Are you sure you want to delete <strong>{userToDelete?.username}</strong>? This action cannot be undone.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete}>Delete User</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function AdminUsersPage() {
  return (<AdminGuard><AdminUsersPageContent /></AdminGuard>);
}

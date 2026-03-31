import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { AdminGuard } from "@/components/auth/RoleGuard";
import { useAuthStore } from "@/stores/useAuthStore";
import apiClient from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Search,
  Trash2,
  Loader2,
  UserX,
  Users,
  Pencil,
  KeyRound,
} from "lucide-react";

type UserRole = "superadmin" | "admin" | "member" | "viewer";

interface User {
  id: number;
  username: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

interface Group {
  id: number;
  name: string;
  description: string | null;
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

  // Edit User Dialog State
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [userToEdit, setUserToEdit] = useState<User | null>(null);
  const [editFullName, setEditFullName] = useState("");
  const [editRole, setEditRole] = useState<UserRole>("member");
  const [isSavingEdit, setIsSavingEdit] = useState(false);

  // Password Reset Dialog State
  const [passwordDialogOpen, setPasswordDialogOpen] = useState(false);
  const [userToResetPassword, setUserToResetPassword] = useState<User | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isResettingPassword, setIsResettingPassword] = useState(false);
  const [mustChangePassword, setMustChangePassword] = useState(false);

  // Manage Groups Sheet State
  const [groupsSheetOpen, setGroupsSheetOpen] = useState(false);
  const [userForGroups, setUserForGroups] = useState<User | null>(null);
  const [allGroups, setAllGroups] = useState<Group[]>([]);
  const [selectedGroupIds, setSelectedGroupIds] = useState<number[]>([]);
  const [groupsSearchQuery, setGroupsSearchQuery] = useState("");
  const [isLoadingGroups, setIsLoadingGroups] = useState(false);
  const [isSavingGroups, setIsSavingGroups] = useState(false);

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

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleRoleChange = async (userId: number, newRole: UserRole) => {
    setUpdatingUserId(userId);
    try {
      await apiClient.patch(`/users/${userId}/role`, { role: newRole });
      setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, role: newRole } : u)));
      toast.success("Role updated successfully");
    } catch (err) {
      toast.error("Failed to update role");
    } finally {
      setUpdatingUserId(null);
    }
  };

  const handleActiveToggle = async (userId: number, isActive: boolean) => {
    setUpdatingUserId(userId);
    try {
      await apiClient.patch(`/users/${userId}/active`, { is_active: isActive });
      setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, is_active: isActive } : u)));
      toast.success(`User ${isActive ? "activated" : "deactivated"} successfully`);
    } catch (err) {
      toast.error("Failed to update user status");
    } finally {
      setUpdatingUserId(null);
    }
  };

  const handleDelete = async () => {
    if (!userToDelete) return;
    try {
      await apiClient.delete(`/users/${userToDelete.id}`);
      setUsers((prev) => prev.filter((u) => u.id !== userToDelete.id));
      toast.success("User deleted successfully");
      setDeleteDialogOpen(false);
      setUserToDelete(null);
    } catch (err) {
      toast.error("Failed to delete user");
    }
  };

  // Edit User Handlers
  const openEditDialog = (user: User) => {
    setUserToEdit(user);
    setEditFullName(user.full_name);
    setEditRole(user.role);
    setEditDialogOpen(true);
  };

  const closeEditDialog = () => {
    setEditDialogOpen(false);
    setUserToEdit(null);
    setEditFullName("");
    setEditRole("member");
  };

  const handleSaveEdit = async () => {
    if (!userToEdit) return;
    setIsSavingEdit(true);
    try {
      await apiClient.patch(`/users/${userToEdit.id}`, {
        full_name: editFullName,
        role: editRole,
      });
      setUsers((prev) =>
        prev.map((u) =>
          u.id === userToEdit.id ? { ...u, full_name: editFullName, role: editRole } : u
        )
      );
      toast.success("User updated successfully");
      closeEditDialog();
    } catch (err) {
      toast.error("Failed to update user");
    } finally {
      setIsSavingEdit(false);
    }
  };

  // Password Reset Handlers
  const openPasswordDialog = (user: User) => {
    setUserToResetPassword(user);
    setNewPassword("");
    setConfirmPassword("");
    setMustChangePassword(false);
    setPasswordDialogOpen(true);
  };

  const closePasswordDialog = () => {
    setPasswordDialogOpen(false);
    setUserToResetPassword(null);
    setNewPassword("");
    setConfirmPassword("");
    setMustChangePassword(false);
  };

  const handleResetPassword = async () => {
    if (!userToResetPassword) return;
    if (newPassword !== confirmPassword) {
      toast.error("Passwords do not match");
      return;
    }
    if (newPassword.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    setIsResettingPassword(true);
    try {
      const response = await apiClient.patch(`/users/${userToResetPassword.id}/password`, {
        new_password: newPassword,
      });
      setMustChangePassword(response.data.must_change_password ?? true);
      toast.success("Password reset successfully");
      closePasswordDialog();
    } catch (err) {
      toast.error("Failed to reset password");
    } finally {
      setIsResettingPassword(false);
    }
  };

  // Manage Groups Handlers
  const fetchAllGroups = async () => {
    try {
      const response = await apiClient.get<{ groups: Group[] }>("/groups");
      setAllGroups(response.data.groups);
    } catch (err) {
      console.error("Failed to fetch groups:", err);
      toast.error("Failed to load groups");
    }
  };

  const fetchUserGroups = async (userId: number) => {
    try {
      const response = await apiClient.get<{ groups: Group[] }>(`/users/${userId}/groups`);
      setSelectedGroupIds(response.data.groups.map((g) => g.id));
    } catch (err) {
      console.error("Failed to fetch user groups:", err);
      toast.error("Failed to load user groups");
    }
  };

  const openGroupsSheet = async (user: User) => {
    setUserForGroups(user);
    setGroupsSheetOpen(true);
    setIsLoadingGroups(true);
    setGroupsSearchQuery("");
    await Promise.all([fetchAllGroups(), fetchUserGroups(user.id)]);
    setIsLoadingGroups(false);
  };

  const closeGroupsSheet = () => {
    setGroupsSheetOpen(false);
    setUserForGroups(null);
    setAllGroups([]);
    setSelectedGroupIds([]);
    setGroupsSearchQuery("");
  };

  const toggleGroup = useCallback((groupId: number) => {
    setSelectedGroupIds((prev) =>
      prev.includes(groupId) ? prev.filter((id) => id !== groupId) : [...prev, groupId]
    );
  }, []);

  const handleSaveGroups = async () => {
    if (!userForGroups) return;
    setIsSavingGroups(true);
    try {
      await apiClient.put(`/users/${userForGroups.id}/groups`, {
        group_ids: selectedGroupIds,
      });
      toast.success("Groups updated successfully");
      closeGroupsSheet();
    } catch (err) {
      toast.error("Failed to update groups");
    } finally {
      setIsSavingGroups(false);
    }
  };

  const filteredGroups = allGroups.filter((group) => {
    const searchLower = groupsSearchQuery.toLowerCase();
    return (
      group.name.toLowerCase().includes(searchLower) ||
      (group.description && group.description.toLowerCase().includes(searchLower))
    );
  });

  const filteredUsers = (users ?? []).filter(
    (u) =>
      u.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
      u.full_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const formatDate = (dateStr: string) => new Date(dateStr).toLocaleDateString();
  const isSuperAdmin = currentUser?.role === "superadmin";
  const canDeleteUser = (user: User) => isSuperAdmin && user.id !== currentUser?.id;
  const canManageUser = (user: User) => user.id !== currentUser?.id;

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
              <Input
                placeholder="Search by username or name..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
                aria-label="Search users"
              />
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
                  <th scope="col" className="text-left p-4 font-medium">
                    Username
                  </th>
                  <th scope="col" className="text-left p-4 font-medium">
                    Full Name
                  </th>
                  <th scope="col" className="text-left p-4 font-medium">
                    Role
                  </th>
                  <th scope="col" className="text-left p-4 font-medium">
                    Status
                  </th>
                  <th scope="col" className="text-left p-4 font-medium">
                    Created
                  </th>
                  <th scope="col" className="text-right p-4 font-medium">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={6} className="p-8 text-center">
                      <Loader2
                        className="w-6 h-6 animate-spin mx-auto text-muted-foreground"
                        role="status"
                        aria-live="polite"
                      />
                      <span className="sr-only">Loading users</span>
                    </td>
                  </tr>
                ) : filteredUsers.length === 0 ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="p-8 text-center text-muted-foreground"
                      role="status"
                      aria-live="polite"
                    >
                      {searchQuery ? "No users match your search" : "No users found"}
                    </td>
                  </tr>
                ) : (
                  filteredUsers.map((user) => (
                    <tr key={user.id} className="border-b hover:bg-muted/50">
                      <td className="p-4 font-medium">{user.username}</td>
                      <td className="p-4">{user.full_name}</td>
                      <td className="p-4">
                        <select
                          value={user.role}
                          onChange={(e) => handleRoleChange(user.id, e.target.value as UserRole)}
                          disabled={updatingUserId === user.id || user.id === currentUser?.id}
                          aria-label={`Change role for ${user.username}`}
                          className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {ROLE_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="p-4">
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            role="switch"
                            aria-checked={user.is_active}
                            aria-label={`${user.is_active ? "Deactivate" : "Activate"} user ${user.username}`}
                            onClick={() => handleActiveToggle(user.id, !user.is_active)}
                            disabled={updatingUserId === user.id || user.id === currentUser?.id}
                            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${
                              user.is_active ? "bg-primary" : "bg-input"
                            }`}
                          >
                            <span
                              className={`inline-block h-5 w-5 rounded-full bg-background shadow transition-transform ${
                                user.is_active ? "translate-x-5" : "translate-x-0.5"
                              }`}
                            />
                          </button>
                          <Badge variant={user.is_active ? "default" : "secondary"}>
                            {user.is_active ? "Active" : "Inactive"}
                          </Badge>
                        </div>
                      </td>
                      <td className="p-4 text-muted-foreground">{formatDate(user.created_at)}</td>
                      <td className="p-4 text-right">
                        <div className="flex items-center justify-end gap-1">
                          {canManageUser(user) && (
                            <>
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => openGroupsSheet(user)}
                                aria-label={`Manage groups for ${user.username}`}
                                title="Manage Groups"
                              >
                                <Users className="w-4 h-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => openEditDialog(user)}
                                aria-label={`Edit user ${user.username}`}
                                title="Edit User"
                              >
                                <Pencil className="w-4 h-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => openPasswordDialog(user)}
                                aria-label={`Reset password for ${user.username}`}
                                title="Reset Password"
                              >
                                <KeyRound className="w-4 h-4" />
                              </Button>
                            </>
                          )}
                          {canDeleteUser(user) && (
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => {
                                setUserToDelete(user);
                                setDeleteDialogOpen(true);
                              }}
                              aria-label={`Delete user ${user.username}`}
                              className="text-destructive hover:text-destructive hover:bg-destructive/10"
                            >
                              <Trash2 className="w-4 h-4" />
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Delete User Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent aria-labelledby="delete-title" aria-describedby="delete-desc">
          <DialogHeader>
            <DialogTitle id="delete-title" className="flex items-center gap-2">
              <UserX className="w-5 h-5 text-destructive" />
              Delete User
            </DialogTitle>
            <DialogDescription id="delete-desc">
              Are you sure you want to delete <strong>{userToDelete?.username}</strong>? This action
              cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete}>
              Delete User
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit User Dialog */}
      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent aria-labelledby="edit-title" aria-describedby="edit-desc">
          <DialogHeader>
            <DialogTitle id="edit-title" className="flex items-center gap-2">
              <Pencil className="w-5 h-5" />
              Edit User
            </DialogTitle>
            <DialogDescription id="edit-desc">
              Update user details for <strong>{userToEdit?.username}</strong>.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="edit-username">Username</Label>
              <Input
                id="edit-username"
                value={userToEdit?.username ?? ""}
                disabled
                aria-readonly="true"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-fullname">Full Name</Label>
              <Input
                id="edit-fullname"
                value={editFullName}
                onChange={(e) => setEditFullName(e.target.value)}
                placeholder="Enter full name"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-role">Role</Label>
              <select
                id="edit-role"
                value={editRole}
                onChange={(e) => setEditRole(e.target.value as UserRole)}
                className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {ROLE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeEditDialog} disabled={isSavingEdit}>
              Cancel
            </Button>
            <Button onClick={handleSaveEdit} disabled={isSavingEdit}>
              {isSavingEdit ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                "Save Changes"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Password Reset Dialog */}
      <Dialog open={passwordDialogOpen} onOpenChange={setPasswordDialogOpen}>
        <DialogContent aria-labelledby="password-title" aria-describedby="password-desc">
          <DialogHeader>
            <DialogTitle id="password-title" className="flex items-center gap-2">
              <KeyRound className="w-5 h-5" />
              Reset Password
            </DialogTitle>
            <DialogDescription id="password-desc">
              Set a new password for <strong>{userToResetPassword?.username}</strong>.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="new-password">New Password</Label>
              <Input
                id="new-password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Enter new password"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm-password">Confirm Password</Label>
              <Input
                id="confirm-password"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Confirm new password"
              />
            </div>
            {mustChangePassword && (
              <p className="text-sm text-muted-foreground">
                User will be required to change their password on next login.
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closePasswordDialog} disabled={isResettingPassword}>
              Cancel
            </Button>
            <Button onClick={handleResetPassword} disabled={isResettingPassword}>
              {isResettingPassword ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Resetting...
                </>
              ) : (
                "Reset Password"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Manage Groups Sheet */}
      <Sheet open={groupsSheetOpen} onOpenChange={setGroupsSheetOpen}>
        <SheetContent
          className="sm:max-w-[400px] flex flex-col"
          aria-labelledby="groups-title"
          aria-describedby="groups-desc"
        >
          <SheetHeader>
            <SheetTitle id="groups-title" className="flex items-center gap-2">
              <Users className="h-5 w-5" aria-hidden="true" />
              Manage Groups
            </SheetTitle>
            <SheetDescription id="groups-desc">
              Manage group memberships for <strong>{userForGroups?.username}</strong>. Select groups
              to add or remove from this user.
            </SheetDescription>
          </SheetHeader>

          <div className="flex-1 flex flex-col py-4 min-h-0">
            {/* Search Input */}
            <div className="relative mb-4">
              <Search
                className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <Input
                placeholder="Search groups..."
                value={groupsSearchQuery}
                onChange={(e) => setGroupsSearchQuery(e.target.value)}
                className="pl-10"
                aria-label="Search groups"
                disabled={isLoadingGroups}
              />
            </div>

            {/* Groups List */}
            <ScrollArea className="flex-1 -mx-6 px-6">
              {isLoadingGroups ? (
                <div className="space-y-3">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="flex items-center gap-3 p-3 rounded-md border">
                      <Skeleton className="h-4 w-4" />
                      <div className="flex-1 space-y-2">
                        <Skeleton className="h-4 w-32" />
                        <Skeleton className="h-3 w-24" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : filteredGroups.length === 0 ? (
                <div
                  className="text-center py-8 text-muted-foreground"
                  role="status"
                  aria-live="polite"
                >
                  {groupsSearchQuery ? "No groups match your search" : "No groups available"}
                </div>
              ) : (
                <div className="space-y-2 pr-4">
                  {filteredGroups.map((group) => (
                    <div
                      key={group.id}
                      className="flex items-start space-x-3 rounded-md border p-3 hover:bg-muted/50 transition-colors"
                    >
                      <Checkbox
                        id={`group-${group.id}`}
                        checked={selectedGroupIds.includes(group.id)}
                        onCheckedChange={() => toggleGroup(group.id)}
                        aria-label={`Select ${group.name}`}
                        disabled={isSavingGroups}
                      />
                      <Label
                        htmlFor={`group-${group.id}`}
                        className="flex-1 cursor-pointer space-y-1"
                      >
                        <div className="font-medium">{group.name}</div>
                        {group.description && (
                          <div className="text-sm text-muted-foreground">{group.description}</div>
                        )}
                      </Label>
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>

            {/* Selected Count */}
            <div className="mt-4 text-sm text-muted-foreground">
              {selectedGroupIds.length} group{selectedGroupIds.length !== 1 ? "s" : ""} selected
            </div>
          </div>

          <SheetFooter className="flex-col gap-2 sm:flex-row border-t pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={closeGroupsSheet}
              disabled={isSavingGroups}
              className="w-full sm:w-auto"
            >
              Cancel
            </Button>
            <Button
              onClick={handleSaveGroups}
              disabled={isSavingGroups || isLoadingGroups}
              className="w-full sm:w-auto"
              aria-label="Save group changes"
            >
              {isSavingGroups ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                  Saving...
                </>
              ) : (
                "Save Changes"
              )}
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </div>
  );
}

export default function AdminUsersPage() {
  return (
    <AdminGuard>
      <AdminUsersPageContent />
    </AdminGuard>
  );
}

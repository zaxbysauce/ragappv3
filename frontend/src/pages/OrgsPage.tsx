import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { useAuthStore } from "@/stores/useAuthStore";
import apiClient from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AdminGuard } from "@/components/auth/RoleGuard";
import { Building2, Plus, Trash2, Users, Vault, ChevronDown, ChevronUp, Loader2, UserPlus, UserX } from "lucide-react";

type OrgRole = "admin" | "member";

interface OrgMember {
  user_id: number;
  username: string;
  full_name: string;
  role: OrgRole;
  joined_at: string;
}

interface Organization {
  id: number;
  name: string;
  description: string | null;
  member_count: number;
  vault_count: number;
  created_at: string;
  members?: OrgMember[];
}

const ROLE_OPTIONS: { value: OrgRole; label: string }[] = [
  { value: "admin", label: "Admin" },
  { value: "member", label: "Member" },
];

function OrgsPageContent() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedOrgId, setExpandedOrgId] = useState<number | null>(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [orgToDelete, setOrgToDelete] = useState<Organization | null>(null);
  const [creatingOrg, setCreatingOrg] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");
  const [newOrgDescription, setNewOrgDescription] = useState("");
  const [addingMember, setAddingMember] = useState(false);
  const [newMemberUserId, setNewMemberUserId] = useState("");
  const [newMemberRole, setNewMemberRole] = useState<OrgRole>("member");
  const [updatingMemberId, setUpdatingMemberId] = useState<number | null>(null);
  const [removeMemberDialogOpen, setRemoveMemberDialogOpen] = useState(false);
  const [memberToRemove, setMemberToRemove] = useState<OrgMember | null>(null);
  const [orgForMemberAction, setOrgForMemberAction] = useState<number | null>(null);
  
  const currentUser = useAuthStore((state) => state.user);
  const isSuperAdmin = currentUser?.role === "superadmin";

  const fetchOrgs = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiClient.get<{ organizations: Organization[]; total: number }>("/organizations/");
      setOrgs(Array.isArray(response.data) ? response.data : response.data.organizations ?? []);
    } catch (err) {
      console.error("Failed to fetch organizations:", err);
      toast.error("Failed to load organizations");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchOrgs(); }, [fetchOrgs]);

  const fetchOrgMembers = useCallback(async (orgId: number) => {
    try {
      const response = await apiClient.get<{ members: OrgMember[] }>(`/organizations/${orgId}/members`);
      setOrgs((prev) => prev.map((o) => o.id === orgId ? { ...o, members: response.data.members } : o));
    } catch (err) {
      console.error("Failed to fetch members:", err);
      toast.error("Failed to load members");
    }
  }, []);

  const toggleExpand = (orgId: number) => {
    if (expandedOrgId === orgId) {
      setExpandedOrgId(null);
    } else {
      setExpandedOrgId(orgId);
      const org = orgs.find((o) => o.id === orgId);
      if (!org?.members) {
        fetchOrgMembers(orgId);
      }
    }
  };

  const handleCreateOrg = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newOrgName.trim()) return;
    setCreatingOrg(true);
    try {
      const response = await apiClient.post<Organization>("/organizations/", {
        name: newOrgName.trim(),
        description: newOrgDescription.trim() || null,
      });
      setOrgs((prev) => [...prev, response.data]);
      toast.success("Organization created successfully");
      setCreateDialogOpen(false);
      setNewOrgName("");
      setNewOrgDescription("");
    } catch (err) {
      toast.error("Failed to create organization");
    } finally {
      setCreatingOrg(false);
    }
  };

  const handleDeleteOrg = async () => {
    if (!orgToDelete) return;
    try {
      await apiClient.delete(`/organizations/${orgToDelete.id}`);
      setOrgs((prev) => prev.filter((o) => o.id !== orgToDelete.id));
      toast.success("Organization deleted successfully");
      setDeleteDialogOpen(false);
      setOrgToDelete(null);
    } catch (err) {
      toast.error("Failed to delete organization");
    }
  };

  const handleAddMember = async (e: React.FormEvent, orgId: number) => {
    e.preventDefault();
    if (!newMemberUserId.trim()) return;
    const userId = parseInt(newMemberUserId, 10);
    if (isNaN(userId)) { toast.error("Please enter a valid user ID"); return; }
    setAddingMember(true);
    setOrgForMemberAction(orgId);
    try {
      await apiClient.post(`/organizations/${orgId}/members`, { user_id: userId, role: newMemberRole });
      toast.success("Member added to organization");
      setNewMemberUserId("");
      setNewMemberRole("member");
      fetchOrgMembers(orgId);
      // Update member count
      setOrgs((prev) => prev.map((o) => o.id === orgId ? { ...o, member_count: o.member_count + 1 } : o));
    } catch (err) {
      toast.error("Failed to add member");
    } finally {
      setAddingMember(false);
      setOrgForMemberAction(null);
    }
  };

  const handleRoleChange = async (orgId: number, userId: number, newRole: OrgRole) => {
    setUpdatingMemberId(userId);
    try {
      await apiClient.patch(`/organizations/${orgId}/members/${userId}`, { role: newRole });
      setOrgs((prev) => prev.map((o) => {
        if (o.id !== orgId || !o.members) return o;
        return {
          ...o,
          members: o.members.map((m) => m.user_id === userId ? { ...m, role: newRole } : m),
        };
      }));
      toast.success("Role updated successfully");
    } catch (err) {
      toast.error("Failed to update role");
    } finally {
      setUpdatingMemberId(null);
    }
  };

  const handleRemoveMember = async () => {
    if (!memberToRemove || !orgForMemberAction) return;
    try {
      await apiClient.delete(`/organizations/${orgForMemberAction}/members/${memberToRemove.user_id}`);
      setOrgs((prev) => prev.map((o) => {
        if (o.id !== orgForMemberAction || !o.members) return o;
        return {
          ...o,
          members: o.members.filter((m) => m.user_id !== memberToRemove.user_id),
          member_count: o.member_count - 1,
        };
      }));
      toast.success("Member removed from organization");
      setRemoveMemberDialogOpen(false);
      setMemberToRemove(null);
      setOrgForMemberAction(null);
    } catch (err) {
      toast.error("Failed to remove member");
    }
  };

  const formatDate = (dateStr: string) => new Date(dateStr).toLocaleDateString();

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Organizations</h1>
          <p className="text-muted-foreground mt-1">Manage organizations and their members</p>
        </div>
        <Button onClick={() => setCreateDialogOpen(true)}>
          <Plus className="w-4 h-4 mr-2" />Create Organization
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" role="status" aria-live="polite" />
          <span className="sr-only">Loading organizations</span>
        </div>
      ) : orgs.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground" role="status" aria-live="polite">
          No organizations found. Create one to get started.
        </div>
      ) : (
        <div className="space-y-4">
          {orgs.map((org) => (
            <Card key={org.id} className="overflow-hidden">
              <CardHeader className="pb-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                      <Building2 className="w-5 h-5 text-primary" />
                    </div>
                    <div>
                      <CardTitle className="text-lg">{org.name}</CardTitle>
                      {org.description && (
                        <CardDescription>{org.description}</CardDescription>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="flex items-center gap-1">
                      <Users className="w-3 h-3" />{org.member_count}
                    </Badge>
                    <Badge variant="secondary" className="flex items-center gap-1">
                      <Vault className="w-3 h-3" />{org.vault_count}
                    </Badge>
                    <Button variant="ghost" size="icon" onClick={() => toggleExpand(org.id)} aria-label={expandedOrgId === org.id ? "Collapse" : "Expand"}>
                      {expandedOrgId === org.id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </Button>
                    {isSuperAdmin && (
                      <Button variant="ghost" size="icon" onClick={() => { setOrgToDelete(org); setDeleteDialogOpen(true); }} aria-label={`Delete organization ${org.name}`} className="text-destructive hover:text-destructive hover:bg-destructive/10">
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    )}
                  </div>
                </div>
              </CardHeader>
              {expandedOrgId === org.id && (
                <CardContent className="border-t pt-4">
                  <form onSubmit={(e) => handleAddMember(e, org.id)} className="flex gap-2 items-end mb-4">
                    <div className="flex-1 space-y-2">
                      <label htmlFor={`org-member-userid-${org.id}`} className="text-sm font-medium">User ID</label>
                      <Input id={`org-member-userid-${org.id}`} placeholder="Enter user ID..." value={newMemberUserId} onChange={(e) => setNewMemberUserId(e.target.value)} disabled={addingMember && orgForMemberAction === org.id} aria-label="User ID to add as organization member" />
                    </div>
                    <div className="space-y-2">
                      <label htmlFor={`org-member-role-${org.id}`} className="text-sm font-medium">Role</label>
                      <select id={`org-member-role-${org.id}`} value={newMemberRole} onChange={(e) => setNewMemberRole(e.target.value as OrgRole)} disabled={addingMember && orgForMemberAction === org.id} aria-label="Role for new member" className="h-10 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring">
                        {ROLE_OPTIONS.map((opt) => (<option key={opt.value} value={opt.value}>{opt.label}</option>))}
                      </select>
                    </div>
                    <Button type="submit" disabled={addingMember && orgForMemberAction === org.id || !newMemberUserId.trim()}>
                      {addingMember && orgForMemberAction === org.id ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <UserPlus className="w-4 h-4 mr-2" />}
                      Add
                    </Button>
                  </form>

                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <caption className="sr-only">Organization Members</caption>
                      <thead>
                        <tr className="border-b">
                          <th scope="col" className="text-left py-2 font-medium">User</th>
                          <th scope="col" className="text-left py-2 font-medium">Role</th>
                          <th scope="col" className="text-left py-2 font-medium">Joined</th>
                          <th scope="col" className="text-right py-2 font-medium">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {!org.members ? (
                          <tr><td colSpan={4} className="py-8 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" role="status" aria-live="polite" /><span className="sr-only">Loading members</span></td></tr>
                        ) : org.members.length === 0 ? (
                          <tr><td colSpan={4} className="py-8 text-center text-muted-foreground" role="status" aria-live="polite">No members yet.</td></tr>
                        ) : (
                          org.members.map((member) => (
                            <tr key={member.user_id} className="border-b last:border-0">
                              <td className="py-3">
                                <div>
                                  <div className="font-medium">{member.full_name || member.username}</div>
                                  <div className="text-sm text-muted-foreground">@{member.username}</div>
                                </div>
                              </td>
                              <td className="py-3">
                                <select value={member.role} onChange={(e) => handleRoleChange(org.id, member.user_id, e.target.value as OrgRole)} disabled={updatingMemberId === member.user_id} aria-label={`Change role for ${member.username}`} className="h-8 rounded-md border border-input bg-background px-2 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50">
                                  {ROLE_OPTIONS.map((opt) => (<option key={opt.value} value={opt.value}>{opt.label}</option>))}
                                </select>
                              </td>
                              <td className="py-3 text-muted-foreground text-sm">{formatDate(member.joined_at)}</td>
                              <td className="py-3 text-right">
                                <Button variant="ghost" size="icon" onClick={() => { setMemberToRemove(member); setOrgForMemberAction(org.id); setRemoveMemberDialogOpen(true); }} aria-label={`Remove ${member.username} from organization`} className="text-destructive hover:text-destructive hover:bg-destructive/10">
                                  <UserX className="w-4 h-4" />
                                </Button>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              )}
            </Card>
          ))}
        </div>
      )}

      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent aria-labelledby="create-org-title" aria-describedby="create-org-desc">
          <form onSubmit={handleCreateOrg}>
            <DialogHeader>
              <DialogTitle id="create-org-title" className="flex items-center gap-2">
                <Building2 className="w-5 h-5" />Create Organization
              </DialogTitle>
              <DialogDescription id="create-org-desc">Create a new organization to group users and vaults.</DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <label htmlFor="org-name" className="text-sm font-medium">Name</label>
                <Input id="org-name" placeholder="Organization name..." value={newOrgName} onChange={(e) => setNewOrgName(e.target.value)} disabled={creatingOrg} required aria-label="Organization name" />
              </div>
              <div className="space-y-2">
                <label htmlFor="org-description" className="text-sm font-medium">Description</label>
                <Input id="org-description" placeholder="Description (optional)..." value={newOrgDescription} onChange={(e) => setNewOrgDescription(e.target.value)} disabled={creatingOrg} aria-label="Organization description" />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreateDialogOpen(false)} disabled={creatingOrg}>Cancel</Button>
              <Button type="submit" disabled={creatingOrg || !newOrgName.trim()}>
                {creatingOrg && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                Create
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent aria-labelledby="delete-org-title" aria-describedby="delete-org-desc">
          <DialogHeader>
            <DialogTitle id="delete-org-title" className="flex items-center gap-2">
              <Trash2 className="w-5 h-5 text-destructive" />Delete Organization
            </DialogTitle>
            <DialogDescription id="delete-org-desc">Are you sure you want to delete <strong>{orgToDelete?.name}</strong>? This action cannot be undone.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDeleteOrg}>Delete Organization</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={removeMemberDialogOpen} onOpenChange={setRemoveMemberDialogOpen}>
        <DialogContent aria-labelledby="remove-member-title" aria-describedby="remove-member-desc">
          <DialogHeader>
            <DialogTitle id="remove-member-title" className="flex items-center gap-2">
              <UserX className="w-5 h-5 text-destructive" />Remove Member
            </DialogTitle>
            <DialogDescription id="remove-member-desc">Are you sure you want to remove <strong>{memberToRemove?.full_name || memberToRemove?.username}</strong> from this organization?</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setRemoveMemberDialogOpen(false); setMemberToRemove(null); setOrgForMemberAction(null); }}>Cancel</Button>
            <Button variant="destructive" onClick={handleRemoveMember}>Remove</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function OrgsPage() {
  return (<AdminGuard><OrgsPageContent /></AdminGuard>);
}

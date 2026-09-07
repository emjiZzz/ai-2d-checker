import { useState } from "react";
import { useAdminUsers } from "../../../hooks/useAdminUsers";
import { useQueryClient } from "@tanstack/react-query";
import { adminUserKeys } from "../../../services/queryKeys";
import type { EnterpriseUser } from "../../../stores/adminStore";

export const useUserManagement = () => {
  const {
    users,
    isLoading,
    isFetching,
    error: queryError,
    isCreating,
    isDeleting,
    isUpdating,
    mutationError,
    createUser,
    deleteUser,
    updateUser,
  } = useAdminUsers();

  const queryClient = useQueryClient();

  // storeError surfaces either a query error or a mutation error so the
  // existing toast infrastructure in UserManagement.tsx requires no changes.
  const storeError = (queryError ?? mutationError)?.message ?? null;

  // fetchUsers is exposed so the manual "Sync Directory" button still works.
  // It simply tells TanStack Query the list is stale — a refetch fires
  // immediately if the component is mounted.
  const fetchUsers = () =>
    queryClient.invalidateQueries({ queryKey: adminUserKeys.lists() });

  // Local state variables (pure UI state — correct home is useState)
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState("user");
  const [showCreatePassword, setShowCreatePassword] = useState(false);

  // Searching / Filtering
  const [searchQuery, setSearchQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<"all" | "admin" | "user">("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "inactive">("all");

  // Reset password states
  const [resettingUser, setResettingUser] = useState<string | null>(null);
  const [resetPasswordText, setResetPasswordText] = useState("");
  const [showResetPassword, setShowResetPassword] = useState(false);

  // Edit user states
  const [editingUser, setEditingUser] = useState<EnterpriseUser | null>(null);
  const [editRole, setEditRole] = useState("user");

  // Success / Error toast indicators
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  // Confirmation overlay for destructive deletion
  const [deletingUser, setDeletingUser] = useState<string | null>(null);


  const generateSecurePassword = () => {
    const chars = "abcdefghijklmnopqrstuvwxyz";
    const caps = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    const nums = "0123456789";
    const specs = "!@#$%^&*";
    let pass = "";
    for (let i = 0; i < 4; i++) pass += chars[Math.floor(Math.random() * chars.length)];
    for (let i = 0; i < 4; i++) pass += caps[Math.floor(Math.random() * caps.length)];
    for (let i = 0; i < 3; i++) pass += nums[Math.floor(Math.random() * nums.length)];
    pass += specs[Math.floor(Math.random() * specs.length)];
    return pass;
  };

  const handleGenerateCreatePassword = () => {
    const generated = generateSecurePassword();
    setNewPassword(generated);
    setShowCreatePassword(true);
    triggerNotification("Secure password generated successfully!");
  };

  const handleGenerateResetPassword = () => {
    const generated = generateSecurePassword();
    setResetPasswordText(generated);
    setShowResetPassword(true);
  };

  const triggerNotification = (msg: string) => {
    setSuccessMessage(msg);
    setTimeout(() => setSuccessMessage(null), 4000);
  };

  const triggerError = (msg: string) => {
    setLocalError(msg);
    setTimeout(() => setLocalError(null), 4000);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUsername.trim() || !newPassword.trim()) return;

    try {
      await createUser({ username: newUsername.trim(), password: newPassword, role: newRole });
      setNewUsername("");
      setNewPassword("");
      triggerNotification(`Account created successfully for: ${newUsername}`);
    } catch (err: any) {
      triggerError(err?.message ?? storeError ?? "Failed to register enterprise account.");
    }
  };

  const handleToggleActive = async (username: string, currentActive: boolean) => {
    if (username === "admin") {
      triggerError("Cannot lock or deactivate the default system administrator.");
      return;
    }

    try {
      await updateUser(username, { active: !currentActive });
      triggerNotification(
        `User account ${username} successfully ${
          !currentActive ? "unlocked & activated" : "locked & suspended"
        }.`
      );
    } catch (err: any) {
      triggerError(err?.message ?? storeError ?? "Failed to update account status.");
    }
  };

  const handleResetPasswordSave = async () => {
    if (!resettingUser || !resetPasswordText.trim()) return;

    try {
      await updateUser(resettingUser, { password: resetPasswordText.trim() });
      setResettingUser(null);
      setResetPasswordText("");
      triggerNotification(`Password successfully updated for user: ${resettingUser}`);
    } catch (err: any) {
      triggerError(err?.message ?? storeError ?? "Failed to reset password.");
    }
  };

  const handleEditSave = async () => {
    if (!editingUser) return;
    if (editingUser.username === "admin" && editRole !== "admin") {
      triggerError("Cannot demote the default system administrator.");
      return;
    }

    try {
      await updateUser(editingUser.username, { role: editRole });
      setEditingUser(null);
      triggerNotification(`Account details successfully saved for: ${editingUser.username}`);
    } catch (err: any) {
      triggerError(err?.message ?? storeError ?? "Failed to update account details.");
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deletingUser) return;
    if (deletingUser === "admin") return;

    try {
      await deleteUser(deletingUser);
      triggerNotification(`Permanently purged user registry for: ${deletingUser}`);
    } catch (err: any) {
      triggerError(err?.message ?? storeError ?? "Failed to delete account registry.");
    }
    setDeletingUser(null);
  };

  const totalAccounts = users.length;
  const activeAccounts = users.filter((u) => u.active).length;
  const adminAccounts = users.filter((u) => u.role === "admin").length;
  const auditorAccounts = users.filter((u) => u.role === "user").length;

  const filteredUsers = users.filter((u) => {
    const matchesSearch = u.username.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesRole = roleFilter === "all" || u.role === roleFilter;
    const matchesStatus =
      statusFilter === "all" ||
      (statusFilter === "active" && u.active) ||
      (statusFilter === "inactive" && !u.active);
    return matchesSearch && matchesRole && matchesStatus;
  });

  return {
    users,
    filteredUsers,
    isLoading: isLoading || isCreating || isDeleting || isUpdating,
    isFetching,
    storeError,
    fetchUsers,

    // Form fields
    newUsername, setNewUsername,
    newPassword, setNewPassword,
    newRole, setNewRole,
    showCreatePassword, setShowCreatePassword,

    // Filters
    searchQuery, setSearchQuery,
    roleFilter, setRoleFilter,
    statusFilter, setStatusFilter,

    // Reset password
    resettingUser, setResettingUser,
    resetPasswordText, setResetPasswordText,
    showResetPassword, setShowResetPassword,

    // Edit user
    editingUser, setEditingUser,
    editRole, setEditRole,

    // Deletion
    deletingUser, setDeletingUser,

    // Notifications
    successMessage, setSuccessMessage,
    localError, setLocalError,

    // Metrics
    totalAccounts, activeAccounts, adminAccounts, auditorAccounts,

    // Actions
    handleCreate,
    handleToggleActive,
    handleEditSave,
    handleResetPasswordSave,
    handleDeleteConfirm,
    handleGenerateCreatePassword,
    handleGenerateResetPassword
  };
};

import React from "react";
import { useUserManagement } from "./hooks/useUserManagement";
import { UserTable } from "./components/UserTable";
import { UserModals } from "./components/UserModals";
import { UserMetrics } from "./components/UserMetrics";
import { UserFilterPanel } from "./components/UserFilterPanel";
import { UserRegistrationForm } from "./components/UserRegistrationForm";
import { RefreshCw, CheckCircle2, AlertTriangle, Shield } from "lucide-react";
import { Button } from "../../components/ui/Button";
import "./UserManagement.css";

export const UserManagement: React.FC = () => {
  const {
    filteredUsers,
    isLoading,
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
    successMessage,
    localError,

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
  } = useUserManagement();

  return (
    <div className="admin-subpage">
      {/* Dynamic Slide-Down Floating Toast Notifications */}
      {(successMessage || localError || storeError) && (
        <div className="admin-toast-container">
          {successMessage && (
            <div className="admin-toast success">
              <CheckCircle2 size={16} />
              <span>{successMessage}</span>
            </div>
          )}
          {localError && (
            <div className="admin-toast error">
              <AlertTriangle size={16} />
              <span>{localError}</span>
            </div>
          )}
        </div>
      )}

      {/* SUBPAGE HEADER */}
      <div className="subpage-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 className="section-title">User Account Registry</h2>
          <p className="section-desc">Add, authorize, suspend, or reset credentials for corporate enterprise engineers.</p>
        </div>
        <Button
          variant="secondary"
          onClick={() => fetchUsers()}
          disabled={isLoading}
          className="gap-2"
        >
          <RefreshCw size={14} className={isLoading ? "spin-animation" : ""} />
          Sync Directory
        </Button>
      </div>

      <UserMetrics 
        totalAccounts={totalAccounts}
        activeAccounts={activeAccounts}
        adminAccounts={adminAccounts}
        auditorAccounts={auditorAccounts}
      />

      <UserFilterPanel 
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        roleFilter={roleFilter}
        setRoleFilter={setRoleFilter}
        statusFilter={statusFilter}
        setStatusFilter={setStatusFilter}
      />

      {/* 3. DUAL-GRID LAYOUT */}
      <div className="admin-grid-2" style={{ marginTop: "24px" }}>
        <UserRegistrationForm 
          handleCreate={handleCreate}
          newUsername={newUsername}
          setNewUsername={setNewUsername}
          newPassword={newPassword}
          setNewPassword={setNewPassword}
          newRole={newRole}
          setNewRole={setNewRole}
          showCreatePassword={showCreatePassword}
          setShowCreatePassword={setShowCreatePassword}
          handleGenerateCreatePassword={handleGenerateCreatePassword}
          isLoading={isLoading}
        />

        {/* Directory Listings Card */}
        <div className="card settings-card directory-listings-card" style={{ position: "relative", display: "flex", flexDirection: "column" }}>
          <UserModals
            editingUser={editingUser}
            setEditingUser={setEditingUser}
            editRole={editRole}
            setEditRole={setEditRole}
            handleEditSave={handleEditSave}
            
            resettingUser={resettingUser}
            setResettingUser={setResettingUser}
            resetPasswordText={resetPasswordText}
            setResetPasswordText={setResetPasswordText}
            showResetPassword={showResetPassword}
            setShowResetPassword={setShowResetPassword}
            handleGenerateResetPassword={handleGenerateResetPassword}
            handleResetPasswordSave={handleResetPasswordSave}
            
            deletingUser={deletingUser}
            setDeletingUser={setDeletingUser}
            handleDeleteConfirm={handleDeleteConfirm}
            
            isLoading={isLoading}
          />

          <div className="card-title-row" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 className="card-title" style={{ margin: 0 }}>
              <Shield size={18} style={{ color: "var(--accent-cyan)" }} />
              Active System Users ({filteredUsers.length})
            </h3>
          </div>

          <UserTable
            filteredUsers={filteredUsers}
            isLoading={isLoading}
            handleToggleActive={handleToggleActive}
            setEditingUser={setEditingUser}
            setEditRole={setEditRole}
            setResettingUser={setResettingUser}
            setResetPasswordText={setResetPasswordText}
            setDeletingUser={setDeletingUser}
          />
        </div>
      </div>
    </div>
  );
};

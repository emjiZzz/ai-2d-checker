import React from "react";
import { Search, X } from "lucide-react";
import { Button } from "../../../components/ui/Button";

interface UserFilterPanelProps {
  searchQuery: string;
  setSearchQuery: (val: string) => void;
  roleFilter: "all" | "admin" | "user";
  setRoleFilter: (val: "all" | "admin" | "user") => void;
  statusFilter: "all" | "active" | "inactive";
  setStatusFilter: (val: "all" | "active" | "inactive") => void;
}

export const UserFilterPanel: React.FC<UserFilterPanelProps> = ({
  searchQuery,
  setSearchQuery,
  roleFilter,
  setRoleFilter,
  statusFilter,
  setStatusFilter
}) => {
  return (
    <div className="card filter-control-card">
      <div className="filter-search-group">
        <div className="search-input-wrapper">
          <Search size={16} className="search-icon" />
          <input
            type="text"
            placeholder="Search user directories by username..."
            className="form-input search-input"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <Button variant="ghost" size="icon" className="h-6 w-6 ml-2 absolute right-2" onClick={() => setSearchQuery("")}>
              <X size={14} />
            </Button>
          )}
        </div>

        <div className="filter-segments-wrapper">
          {/* Role Filters */}
          <div className="filter-pill-group">
            <span className="filter-pill-label">Role:</span>
            {(["all", "admin", "user"] as const).map((role) => (
              <Button
                key={role}
                variant={roleFilter === role ? "default" : "outline"}
                size="sm"
                className="h-7 text-xs px-3 rounded-full"
                onClick={() => setRoleFilter(role)}
              >
                {role === "all" ? "All Roles" : role === "admin" ? "Admins" : "Auditors"}
              </Button>
            ))}
          </div>

          {/* Status Filters */}
          <div className="filter-pill-group">
            <span className="filter-pill-label">Status:</span>
            {(["all", "active", "inactive"] as const).map((status) => (
              <Button
                key={status}
                variant={statusFilter === status ? "default" : "outline"}
                size="sm"
                className="h-7 text-xs px-3 rounded-full"
                onClick={() => setStatusFilter(status)}
              >
                {status === "all" ? "All" : status === "active" ? "Active" : "Suspended"}
              </Button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

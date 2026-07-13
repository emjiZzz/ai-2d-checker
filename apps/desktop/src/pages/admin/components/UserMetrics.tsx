import React from "react";
import { User, UserCheck, Shield } from "lucide-react";

interface UserMetricsProps {
  totalAccounts: number;
  activeAccounts: number;
  adminAccounts: number;
  auditorAccounts: number;
}

export const UserMetrics: React.FC<UserMetricsProps> = ({
  totalAccounts,
  activeAccounts,
  adminAccounts,
  auditorAccounts
}) => {
  return (
    <div className="admin-metrics-grid">
      <div className="card metrics-card">
        <div className="metrics-icon-wrapper blue">
          <User size={18} />
        </div>
        <div className="metrics-data">
          <span className="metrics-value">{totalAccounts}</span>
          <span className="metrics-label">Registered Accounts</span>
        </div>
      </div>

      <div className="card metrics-card">
        <div className="metrics-icon-wrapper green">
          <UserCheck size={18} />
        </div>
        <div className="metrics-data">
          <span className="metrics-value">{activeAccounts}</span>
          <span className="metrics-label">Active Directory</span>
        </div>
      </div>

      <div className="card metrics-card">
        <div className="metrics-icon-wrapper purple">
          <Shield size={18} />
        </div>
        <div className="metrics-data">
          <span className="metrics-value">{adminAccounts}</span>
          <span className="metrics-label">System Admins</span>
        </div>
      </div>

      <div className="card metrics-card">
        <div className="metrics-icon-wrapper cyan">
          <User size={18} />
        </div>
        <div className="metrics-data">
          <span className="metrics-value">{auditorAccounts}</span>
          <span className="metrics-label">Auditing Engineers</span>
        </div>
      </div>
    </div>
  );
};

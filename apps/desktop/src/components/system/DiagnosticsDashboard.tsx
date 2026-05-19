import React, { useState } from 'react';

interface BackupRecord {
  name: string;
  date: string;
  sizeMb: number;
}

export const DiagnosticsDashboard: React.FC = () => {
  const [backups, setBackups] = useState<BackupRecord[]>([
    { name: "ai2d_backup_20260518_120000.zip", date: "2026-05-18 12:00:00", sizeMb: 24.5 }
  ]);
  const [storageLimit] = useState({ used: 450, total: 5120 }); // in MB

  const handleBackup = () => {
    // Mock backup creation
    const newBackup: BackupRecord = {
      name: `ai2d_backup_${Date.now()}.zip`,
      date: new Date().toISOString().replace('T', ' ').substring(0, 19),
      sizeMb: 12.8
    };
    setBackups([newBackup, ...backups]);
  };

  const usagePercent = ((storageLimit.used / storageLimit.total) * 100).toFixed(1);

  return (
    <div className="system-dashboard bg-gray-900 text-gray-100 p-6 rounded-lg border border-gray-800 space-y-6 max-w-4xl">
      <h2 className="text-xl font-bold text-blue-400 border-b border-gray-800 pb-3 flex items-center">
        <span className="mr-2">⚙</span> System Operations & Diagnostics
      </h2>

      {/* 1. Storage Quota */}
      <div className="bg-gray-800/50 border border-gray-700 p-4 rounded-lg">
        <h3 className="text-sm font-bold text-gray-200 mb-2">Local Workstation Disk Quota</h3>
        <div className="w-full bg-gray-700 h-4 rounded-full overflow-hidden mb-2">
          <div className="bg-blue-600 h-full transition-all duration-500" style={{ width: `${usagePercent}%` }} />
        </div>
        <div className="flex justify-between text-xs text-gray-400">
          <span>{storageLimit.used} MB Used</span>
          <span>{storageLimit.total} MB Quota ({usagePercent}%)</span>
        </div>
      </div>

      {/* 2. Backup & Recovery */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-gray-800/50 border border-gray-700 p-4 rounded-lg flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-bold text-gray-200 mb-2">Workspace Backup</h3>
            <p className="text-xs text-gray-400 mb-4">
              Enables offline encrypted backups of your CAD layers, annotations, and AI vector collections.
            </p>
          </div>
          <button 
            onClick={handleBackup}
            className="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs py-2 rounded transition-colors"
          >
            Create Encrypted Backup Point
          </button>
        </div>

        <div className="bg-gray-800/50 border border-gray-700 p-4 rounded-lg">
          <h3 className="text-sm font-bold text-gray-200 mb-2">Available Restore Points</h3>
          <div className="space-y-2 max-h-[120px] overflow-y-auto custom-scrollbar">
            {backups.map((bk, i) => (
              <div key={i} className="flex justify-between items-center text-xs bg-gray-800 p-2 rounded border border-gray-700/50">
                <span className="font-mono text-gray-300 truncate max-w-[200px]" title={bk.name}>{bk.name}</span>
                <span className="text-gray-500 font-semibold">{bk.sizeMb} MB</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 3. Local Hardware Capability */}
      <div className="bg-gray-800/50 border border-gray-700 p-4 rounded-lg flex justify-between items-center">
        <div>
          <h4 className="text-sm font-bold text-gray-200">Quantized ONNX Hardware Accelerator</h4>
          <p className="text-xs text-gray-500">Checking for local NVIDIA CUDA or standard CPU fallback settings.</p>
        </div>
        <span className="bg-green-500/20 text-green-400 text-xs font-bold border border-green-500/30 px-3 py-1 rounded">
          Active: CPU (Quantized MiniLM)
        </span>
      </div>
    </div>
  );
};

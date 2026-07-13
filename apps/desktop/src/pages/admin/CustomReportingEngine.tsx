import React, { useState } from 'react';
import { Button } from '../../components/ui/Button';
import { FileText, Download, Filter, Settings, FileSpreadsheet, Send, FileBarChart, Loader2, CheckCircle2 } from 'lucide-react';

export const CustomReportingEngine: React.FC = () => {
  const [reportType, setReportType] = useState<'audit_summary' | 'compliance_full' | 'standards_coverage'>('compliance_full');
  const [exportFormat, setExportFormat] = useState<'pdf' | 'csv' | 'json'>('pdf');
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationSuccess, setGenerationSuccess] = useState(false);
  const [filters, setFilters] = useState({
    critical: true,
    high: true,
    medium: false,
    low: false,
    includeImages: true,
    includeMetrics: true
  });
  const [remarks, setRemarks] = useState('');

  const handleGenerate = () => {
    setIsGenerating(true);
    setGenerationSuccess(false);
    
    // Simulate generation delay
    setTimeout(() => {
      setIsGenerating(false);
      setGenerationSuccess(true);
      
      // Reset success message after 3 seconds
      setTimeout(() => setGenerationSuccess(false), 3000);
    }, 1500);
  };

  return (
    <div className="w-full max-w-5xl mx-auto flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2 m-0 text-text-primary">
            <FileBarChart className="text-purple-500" />
            Custom Reporting Engine
          </h2>
          <p className="text-text-muted text-sm mt-1">Configure, preview, and generate detailed compliance reports.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Configuration */}
        <div className="lg:col-span-2 flex flex-col gap-5">
          
          <div className="bg-bg-card border border-border-color rounded-xl overflow-hidden shadow-sm">
            <div className="bg-bg-dark border-b border-border-color px-4 py-3 font-semibold flex items-center gap-2 text-sm text-text-primary">
              <Settings size={16} className="text-accent-cyan" />
              Report Configuration
            </div>
            <div className="p-5 flex flex-col gap-5">
              
              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium text-text-primary">Report Type</label>
                <div className="flex bg-bg-dark border border-border-color rounded-lg p-1">
                  <button 
                    onClick={() => setReportType('audit_summary')}
                    className={`flex-1 py-2 text-xs font-medium rounded-md transition-colors ${reportType === 'audit_summary' ? 'bg-bg-card shadow-sm text-text-primary' : 'text-text-muted hover:text-text-primary'}`}
                  >
                    Audit Summary
                  </button>
                  <button 
                    onClick={() => setReportType('compliance_full')}
                    className={`flex-1 py-2 text-xs font-medium rounded-md transition-colors ${reportType === 'compliance_full' ? 'bg-bg-card shadow-sm text-text-primary' : 'text-text-muted hover:text-text-primary'}`}
                  >
                    Full Compliance Details
                  </button>
                  <button 
                    onClick={() => setReportType('standards_coverage')}
                    className={`flex-1 py-2 text-xs font-medium rounded-md transition-colors ${reportType === 'standards_coverage' ? 'bg-bg-card shadow-sm text-text-primary' : 'text-text-muted hover:text-text-primary'}`}
                  >
                    Standards Coverage
                  </button>
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium text-text-primary flex items-center gap-2">
                  <Filter size={14} /> Severity Filters
                </label>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {Object.entries({
                    critical: 'Critical',
                    high: 'High',
                    medium: 'Medium',
                    low: 'Low'
                  }).map(([key, label]) => (
                    <label key={key} className="flex items-center gap-2 p-3 bg-bg-dark border border-border-color rounded-lg cursor-pointer hover:border-zinc-700 transition-colors">
                      <input 
                        type="checkbox" 
                        checked={filters[key as keyof typeof filters] as boolean}
                        onChange={() => setFilters(f => ({ ...f, [key]: !f[key as keyof typeof filters] }))}
                        className="rounded border-border-color bg-bg-dark text-accent-cyan focus:ring-accent-cyan focus:ring-offset-bg-card"
                      />
                      <span className="text-sm text-text-primary">{label}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium text-text-primary">Content Options</label>
                <div className="flex flex-col gap-3 p-4 bg-bg-dark border border-border-color rounded-lg">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input 
                      type="checkbox" 
                      checked={filters.includeImages}
                      onChange={() => setFilters(f => ({ ...f, includeImages: !f.includeImages }))}
                      className="rounded border-border-color bg-bg-dark text-accent-cyan"
                    />
                    <span className="text-sm text-text-primary">Include visual CAD overlays and marking snippets</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input 
                      type="checkbox" 
                      checked={filters.includeMetrics}
                      onChange={() => setFilters(f => ({ ...f, includeMetrics: !f.includeMetrics }))}
                      className="rounded border-border-color bg-bg-dark text-accent-cyan"
                    />
                    <span className="text-sm text-text-primary">Include statistical confidence metrics & performance timing</span>
                  </label>
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium text-text-primary">Inspector Remarks (Appended to Report)</label>
                <textarea 
                  className="w-full bg-bg-dark border border-border-color rounded-lg p-3 text-sm text-text-primary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan min-h-[100px] resize-y"
                  placeholder="Enter any custom remarks, sign-off notes, or specific contextual observations..."
                  value={remarks}
                  onChange={(e) => setRemarks(e.target.value)}
                />
              </div>

            </div>
          </div>
        </div>

        {/* Right Column: Export & Preview */}
        <div className="flex flex-col gap-5">
          <div className="bg-bg-card border border-border-color rounded-xl overflow-hidden shadow-sm">
            <div className="bg-bg-dark border-b border-border-color px-4 py-3 font-semibold flex items-center gap-2 text-sm text-text-primary">
              <Download size={16} className="text-emerald-500" />
              Export Options
            </div>
            <div className="p-5 flex flex-col gap-5">
              
              <div className="flex flex-col gap-3">
                <label className="flex items-center justify-between p-3 border border-border-color rounded-lg cursor-pointer transition-colors hover:bg-bg-dark/50" style={{ borderColor: exportFormat === 'pdf' ? 'var(--accent-cyan)' : 'var(--border-color)', background: exportFormat === 'pdf' ? 'rgba(0, 229, 255, 0.05)' : 'transparent' }}>
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded bg-red-500/10 flex items-center justify-center text-red-500">
                      <FileText size={18} />
                    </div>
                    <div className="flex flex-col">
                      <span className="text-sm font-medium text-text-primary">PDF Document</span>
                      <span className="text-xs text-text-muted">Best for sharing & printing</span>
                    </div>
                  </div>
                  <input type="radio" name="format" checked={exportFormat === 'pdf'} onChange={() => setExportFormat('pdf')} className="text-accent-cyan focus:ring-accent-cyan focus:ring-offset-bg-card" />
                </label>

                <label className="flex items-center justify-between p-3 border border-border-color rounded-lg cursor-pointer transition-colors hover:bg-bg-dark/50" style={{ borderColor: exportFormat === 'csv' ? 'var(--accent-cyan)' : 'var(--border-color)', background: exportFormat === 'csv' ? 'rgba(0, 229, 255, 0.05)' : 'transparent' }}>
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded bg-emerald-500/10 flex items-center justify-center text-emerald-500">
                      <FileSpreadsheet size={18} />
                    </div>
                    <div className="flex flex-col">
                      <span className="text-sm font-medium text-text-primary">CSV / Excel</span>
                      <span className="text-xs text-text-muted">Raw data for analysis</span>
                    </div>
                  </div>
                  <input type="radio" name="format" checked={exportFormat === 'csv'} onChange={() => setExportFormat('csv')} className="text-accent-cyan focus:ring-accent-cyan focus:ring-offset-bg-card" />
                </label>

                <label className="flex items-center justify-between p-3 border border-border-color rounded-lg cursor-pointer transition-colors hover:bg-bg-dark/50" style={{ borderColor: exportFormat === 'json' ? 'var(--accent-cyan)' : 'var(--border-color)', background: exportFormat === 'json' ? 'rgba(0, 229, 255, 0.05)' : 'transparent' }}>
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded bg-purple-500/10 flex items-center justify-center text-purple-500">
                      <span className="font-mono font-bold text-xs">{'{}'}</span>
                    </div>
                    <div className="flex flex-col">
                      <span className="text-sm font-medium text-text-primary">JSON Payload</span>
                      <span className="text-xs text-text-muted">System integration format</span>
                    </div>
                  </div>
                  <input type="radio" name="format" checked={exportFormat === 'json'} onChange={() => setExportFormat('json')} className="text-accent-cyan focus:ring-accent-cyan focus:ring-offset-bg-card" />
                </label>
              </div>

              <div className="pt-2">
                <Button 
                  variant="primary" 
                  className="w-full h-12 gap-2 text-[15px]"
                  onClick={handleGenerate}
                  disabled={isGenerating || generationSuccess}
                >
                  {isGenerating ? (
                    <><Loader2 size={18} className="animate-spin" /> Compiling Data...</>
                  ) : generationSuccess ? (
                    <><CheckCircle2 size={18} /> Report Generated!</>
                  ) : (
                    <><Send size={18} /> Generate Report</>
                  )}
                </Button>
              </div>
            </div>
          </div>

          {/* Quick Summary Stats */}
          <div className="bg-bg-card border border-border-color rounded-xl overflow-hidden shadow-sm p-5">
            <h4 className="text-sm font-medium text-text-primary mb-4">Estimated Report Profile</h4>
            
            <div className="flex flex-col gap-3">
              <div className="flex justify-between items-center text-sm">
                <span className="text-text-muted">Total Infractions:</span>
                <span className="font-medium text-text-primary flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-red-500 inline-block mr-1"></span> 24 items
                </span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-text-muted">Filtered Exclusions:</span>
                <span className="font-medium text-text-primary">
                  {(!filters.medium ? 8 : 0) + (!filters.low ? 12 : 0)} items
                </span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-text-muted">Estimated Pages:</span>
                <span className="font-medium text-text-primary">~{filters.includeImages ? 8 : 3} pages</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

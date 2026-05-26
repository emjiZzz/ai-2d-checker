import React, { useState } from 'react';
import { ViolationExplanation } from './ViolationExplanation';
import { GeometryInsightPanel } from './GeometryInsightPanel';
import './CopilotPanel.css';

export const CopilotPanel: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'audit' | 'insights'>('audit');

  return (
    <div className="copilot-panel">
      <h2>
        <span>🤖</span> AI Engineering Copilot
      </h2>

      <div className="copilot-tabs">
        <button
          className={`copilot-tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
          onClick={() => setActiveTab('audit')}
        >
          Compliance Audit
        </button>
        <button
          className={`copilot-tab-btn ${activeTab === 'insights' ? 'active' : ''}`}
          onClick={() => setActiveTab('insights')}
        >
          Geometry Insights
        </button>
      </div>

      <div className="copilot-scroll-area">
        {activeTab === 'audit' ? (
          <ViolationExplanation />
        ) : (
          <GeometryInsightPanel />
        )}
      </div>

      <div className="copilot-input-container">
        <input
          type="text"
          placeholder="Ask copilot about standards or geometry..."
          className="copilot-input"
        />
      </div>
    </div>
  );
};

import React, { useState } from 'react';

interface SearchResult {
  id: string;
  source: string;
  matchPercentage: number;
  snippet: string;
}

export const SemanticSearchPanel: React.FC = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);

  const handleSearch = () => {
    if (!query.trim()) return;
    // Mock local vector search return
    setResults([
      {
        id: "std_405",
        source: "JIS B 0001 (Parallel Keyways)",
        matchPercentage: 94,
        snippet: "Tolerances for keyways on shafts must adhere to the standardized h9/N9 fit classes."
      },
      {
        id: "dwg_002",
        source: "Gear_Assembly_Rev2.dxf",
        matchPercentage: 88,
        snippet: "Matching spline alignment vectors located on 'AM_VIEWS' layer."
      }
    ]);
  };

  return (
    <div className="semantic-search bg-bg-card text-text-primary p-4 rounded-lg border border-border-color">
      <h3 className="text-md font-bold text-accent-cyan mb-3 flex items-center">
        <span className="mr-2">🔍</span> Deep Semantic CAD Search
      </h3>

      <div className="flex space-x-2 mb-4">
        <input 
          type="text" 
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search engineering rules, annotations, or drawing text..."
          className="flex-1 bg-bg-sidebar border border-border-color rounded p-2 text-sm outline-none focus:border-accent-cyan text-text-primary placeholder:text-text-muted"
        />
        <button 
          onClick={handleSearch}
          className="bg-accent-cyan text-on-accent text-sm font-semibold px-4 py-2 rounded transition-colors cursor-pointer"
        >
          Search
        </button>
      </div>

      <div className="space-y-3">
        {results.map(res => (
          <div key={res.id} className="bg-bg-sidebar border border-border-color p-3 rounded hover:border-accent-cyan/50 transition-colors">
            <div className="flex justify-between items-start mb-1">
              <span className="text-xs font-semibold text-accent-cyan uppercase tracking-wider">{res.source}</span>
              <span className="text-[10px] bg-emerald-500/20 text-emerald-500 px-1.5 py-0.5 rounded border border-emerald-500/30">
                {res.matchPercentage}% Match
              </span>
            </div>
            <p className="text-xs text-text-secondary italic">"{res.snippet}"</p>
          </div>
        ))}
      </div>
    </div>
  );
};

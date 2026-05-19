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
    <div className="semantic-search bg-gray-900 text-gray-100 p-4 rounded-lg border border-gray-800">
      <h3 className="text-md font-bold text-blue-400 mb-3 flex items-center">
        <span className="mr-2">🔍</span> Deep Semantic CAD Search
      </h3>

      <div className="flex space-x-2 mb-4">
        <input 
          type="text" 
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search engineering rules, annotations, or drawing text..."
          className="flex-1 bg-gray-800 border border-gray-700 rounded p-2 text-sm outline-none focus:border-blue-500 text-white"
        />
        <button 
          onClick={handleSearch}
          className="bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold px-4 py-2 rounded transition-colors"
        >
          Search
        </button>
      </div>

      <div className="space-y-3">
        {results.map(res => (
          <div key={res.id} className="bg-gray-800/60 border border-gray-700 p-3 rounded hover:border-gray-600 transition-colors">
            <div className="flex justify-between items-start mb-1">
              <span className="text-xs font-semibold text-blue-300 uppercase tracking-wider">{res.source}</span>
              <span className="text-[10px] bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded border border-green-500/30">
                {res.matchPercentage}% Match
              </span>
            </div>
            <p className="text-xs text-gray-300 italic">"{res.snippet}"</p>
          </div>
        ))}
      </div>
    </div>
  );
};

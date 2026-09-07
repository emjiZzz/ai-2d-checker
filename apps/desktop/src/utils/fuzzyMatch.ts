export const normalizeStr = (str: string): string => {
  if (!str) return "";
  let s = str.toLowerCase().trim();
  s = s.replace(/%%c/g, "⌀").replace(/%%d/g, "°").replace(/%%p/g, "±");
  s = s.replace(/ラ/g, "x");
  s = s.replace(/×/g, "x");
  s = s.replace(/:/g, "/");
  return s
    .replace(/[\s\(\)\[\]\{\}\:\;\,\-\_\.\/\引\（\）－−–—―〜～]/g, "")
    .trim();
};

export interface EntityTextPayload {
  text: string;
  x: number;
  y: number;
  handle?: string;
  bbox?: any;
  height?: number;
  layoutSpace?: string;
  layer?: string;
  eType?: string;
}

export const findAllFuzzyMatches = (
  searchTerm: string,
  entities: EntityTextPayload[],
  preferModelSpace: boolean = false,
  allowNumberMismatch: boolean = false,
  minScore: number = 0
): EntityTextPayload[] => {
  if (!searchTerm) return [];

  // Multi-line search terms support (e.g. joined with \n)
  if (searchTerm.includes('\n')) {
    const lines = searchTerm.split('\n').map(l => l.trim()).filter(l => l.length > 1);
    const seen = new Set<string>();
    const combined: EntityTextPayload[] = [];
    for (const line of lines) {
      const lineMatches = findAllFuzzyMatches(line, entities, preferModelSpace, true, minScore);
      for (const m of lineMatches) {
        const key = `${m.x.toFixed(2)},${m.y.toFixed(2)}`;
        if (!seen.has(key)) {
          seen.add(key);
          combined.push(m);
        }
      }
    }
    return combined;
  }

  const normSearch = normalizeStr(searchTerm);
  if (!normSearch) return [];

  const matches: { ent: EntityTextPayload; score: number }[] = [];
  const extractNumbers = (s: string) => {
    const m = s.match(/\d+/g);
    return m ? m.join("") : "";
  };
  const searchNumbers = extractNumbers(normSearch);

  for (const ent of entities) {
    const normEnt = normalizeStr(ent.text);
    if (!normEnt) continue;

    let score = 0;
    if (ent.text.trim() === searchTerm.trim()) {
      score = 105;
    } else if (normEnt === normSearch) {
      score = 100;
    } else if (
      normEnt.replace(/^[0-9]+-/, "") === normSearch ||
      normSearch.replace(/^[0-9]+-/, "") === normEnt ||
      normEnt.replace(/^[crmoo⌀]/i, "") === normSearch ||
      normSearch.replace(/^[crmoo⌀]/i, "") === normEnt
    ) {
      score = 90;
    } else {
      const cleanSearchNum = normSearch.replace(/^[0-9]+-/, "").replace(/^[crmoo⌀]/i, "");
      const cleanEntNum = normEnt.replace(/^[0-9]+-/, "").replace(/^[crmoo⌀]/i, "");
      const fSearch = parseFloat(cleanSearchNum);
      const fEnt = parseFloat(cleanEntNum);
      if (!isNaN(fSearch) && !isNaN(fEnt) && fSearch === fEnt) {
        score = 90;
      } else if (!isNaN(fSearch) && !isNaN(parseFloat(normEnt)) && fSearch === parseFloat(normEnt)) {
        score = 90;
      }
    }

    if (score < 90) {
      const stripLeadDigits = (s: string) => s.replace(/^\d+/, "");
      const strippedSearch = stripLeadDigits(normSearch);
      const strippedEnt = stripLeadDigits(normEnt);
      if (strippedSearch.length >= 2 && strippedSearch === strippedEnt) {
        score = 85;
      } else if (normSearch.includes(normEnt) || normEnt.includes(normSearch)) {
        const minLen = Math.min(normEnt.length, normSearch.length);
        const maxLen = Math.max(normEnt.length, normSearch.length);
        const ratio = minLen / maxLen;
        if (minLen >= 2) {
          score = 50 + ratio * 30;
        }
      } else {
        const searchChars = new Set(normSearch.split(""));
        const entChars = new Set(normEnt.split(""));
        let intersection = 0;
        searchChars.forEach(c => { if (entChars.has(c)) intersection++; });
        const jaccard = intersection / Math.max(searchChars.size, entChars.size);
        if (jaccard > 0.60) {
          score = jaccard * 70;
        } else if (allowNumberMismatch && jaccard > 0.40) {
          score = jaccard * 70;
        }
      }
    }

    if (searchNumbers && !allowNumberMismatch) {
      const entNumbers = extractNumbers(normEnt);
      if (entNumbers && entNumbers !== searchNumbers) {
        score = 0;
      }
    }

    const spaceBonus = (preferModelSpace && ent.layoutSpace === 'Model') ? 5 : 0;
    const effectiveScore = score + spaceBonus;

    if (score > 40) {
      matches.push({ ent, score: effectiveScore });
    }
  }

  if (matches.length === 0) return [];
  const maxScore = Math.max(...matches.map(m => m.score));
  const threshold = maxScore >= 100 ? 100 : (maxScore - 5);
  const finalThreshold = Math.max(threshold, minScore);
  return matches.filter(m => m.score >= finalThreshold).map(m => m.ent);
};

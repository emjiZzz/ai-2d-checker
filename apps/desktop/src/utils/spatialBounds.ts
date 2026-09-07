export const isCoordinateTick = (text: string): boolean => {
  const t = (text || "").trim().toUpperCase();
  if (!t) return true;
  if (t.length === 1 && t >= 'A' && t <= 'Z') return true;
  const num = parseInt(t, 10);
  if (!isNaN(num) && num.toString() === t && num >= 1 && num <= 24) return true;
  return false;
};

export const isStaticLabelOrHeader = (text: string): boolean => {
  const t = (text || "").trim().toLowerCase();
  if (!t) return true;

  const exactStaticTerms = new Set([
    "no.", "no", "and.", "and", "g", "h", "a", "b", "c", "d", "e", "f", "例", "（例）", "こえ", "下", "符号"
  ]);
  if (exactStaticTerms.has(t)) return true;

  const staticTerms = [
    "tolerances", "unless", "otherwise", "specified", "drawings", "表示外公差",
    "finish", "symbol", "roughness", "range", "仕上げ記号", "面粗さ",
    "dimension", "parallelism", "squareness", "length", "寸法区分", "平行度", "直角度",
    "machining", "fabrication", "general", "over", "including",
    "example", "design chg", "chg no", "年月日", "訂正書", "担当", "name", "y/m/d",
    "material", "code", "材質", "寸法", "型式", "個数", "qty", "weight", "重量", "remark", "備考",
    "dwg no", "dwg. no", "図面番号", "title", "名称", "prev. dwg", "previous dwg",
    "scale", "尺度", "date", "日付", "approved", "承認", "checked", "検図", "designed", "設計", "drawn", "製図",
    "job no", "工事番号", "std no", "標準図番号", "mach. code", "機器記号", "unit no", "ユニット",
    "total quantity", "t. q'ty", "総製作個数", "common", "共通番号", "cross ref"
  ];

  return staticTerms.some(term => t.includes(term));
};

export interface Bounds {
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
}

export const computeBounds = (entities: { x: number; y: number; layer?: string }[]): Bounds => {
  if (entities.length === 0) return { xMin: 0, xMax: 1000, yMin: 0, yMax: 1000 };

  const wakuEntities = entities.filter(ent => {
    const layerStr = (ent.layer || "").toLowerCase();
    return ["waku", "border", "frame", "grid", "template", "form", "cosa", "legend", "admin", "block", "table"].some(x => layerStr.includes(x));
  });

  const sourceEntities = wakuEntities.length > 0 ? wakuEntities : entities;

  const getCleanBounds = (vals: number[]) => {
    if (vals.length < 4) return { min: Math.min(...vals), max: Math.max(...vals) };
    const sorted = [...vals].sort((a, b) => a - b);
    const q1 = sorted[Math.floor(sorted.length * 0.25)];
    const q3 = sorted[Math.floor(sorted.length * 0.75)];
    const iqr = q3 - q1;

    const lowerBound = q1 - 2.0 * iqr;
    const upperBound = q3 + 2.0 * iqr;

    const cleanVals = vals.filter(v => v >= lowerBound && v <= upperBound);
    if (cleanVals.length === 0) return { min: Math.min(...vals), max: Math.max(...vals) };

    return { min: Math.min(...cleanVals), max: Math.max(...cleanVals) };
  };

  const xs = sourceEntities.map(e => e.x);
  const ys = sourceEntities.map(e => e.y);

  const xBounds = getCleanBounds(xs);
  const yBounds = getCleanBounds(ys);

  return { xMin: xBounds.min, xMax: xBounds.max, yMin: yBounds.min, yMax: yBounds.max };
};

export interface EngineeringEntityParams {
  ent: { text: string; x: number; y: number; layer?: string; eType?: string };
  drawing: any;
  oldDrawing: any;
  bounds: Bounds;
}

export const isEngineeringDataEntity = ({
  ent,
  drawing,
  oldDrawing,
  bounds
}: EngineeringEntityParams): boolean => {
  const isStructuralAnnotation = ent.eType === 'tolerance' || ent.eType === 'leader' || ent.eType === 'multileader' || ent.eType === 'attrib' || ent.eType === 'insert' || ent.eType === 'mtext' || ent.eType === 'block' || ent.eType === 'dimension' ||
    /^\d*[-]?[CR]\d+(\.\d+)?$/i.test(ent.text.trim().replace(/\s/g, '')) ||
    /^[\u2460-\u2473\u3251-\u325f\u32b1-\u32bf]$/.test(ent.text.trim()) ||
    /^\(\d{1,2}\)$/.test(ent.text.trim()) ||
    /^[\u25bd\u25bf\u25b3\u25b2\u2299\u25ef\u25a1]$/.test(ent.text.trim());

  if (!isStructuralAnnotation) {
    if (isStaticLabelOrHeader(ent.text)) return false;

    const tClean = ent.text.trim().replace(/\s/g, '').toLowerCase();
    const isToleranceRange = /^\d+(\.\d+)?[sS]?(~|〜|-)\d+(\.\d+)?[sS]?$/.test(tClean);
    const isSurfaceFinish = /^\d+(\.\d+)?[sS]$/.test(tClean);
    const isToleranceKw = ["表示外公差", "寸法区分", "平行度", "直角度", "許容差", "仕上ゲ記号", "表面粗さ", "普通寸法許容差", "角度", "長さ", "表示外"].some(kw => ent.text.includes(kw));
    const isToleranceSymbol = ["~", "〜", "±"].includes(tClean);
    if (isToleranceRange || isSurfaceFinish || isToleranceKw || isToleranceSymbol) return false;
  }

  const { xMin, xMax, yMin, yMax } = bounds;
  const width = xMax - xMin;
  const height = yMax - yMin;
  if (width <= 0 || height <= 0) return true;

  const pctX = (ent.x - xMin) / width;
  const pctY = 1.0 - (ent.y - yMin) / height;

  if (pctX < 0.045 || pctX > 0.98 || pctY < 0.045 || pctY > 0.98) return false;

  const isNearMargin = pctX < 0.12 || pctX > 0.88 || pctY < 0.12 || pctY > 0.88;
  if (!isStructuralAnnotation && isNearMargin && isCoordinateTick(ent.text)) return false;

  // -----------------------------------------------------------------------
  // Safe Zone Exclusion (PRIMARY)
  // The backend's content-aware zone_detector sends absolute CAD-coordinate
  // bounding boxes for detected safe zones (tolerance table, etc.).
  // If the entity falls inside ANY safe zone, exclude it immediately.
  // This overrides the legacy percentage-based tolerance table check below.
  // -----------------------------------------------------------------------
  const targetMetadata = (oldDrawing && drawing?.id === oldDrawing.id) ? oldDrawing.metadata : drawing?.metadata;
  const backendSafeZones: Array<[number, number, number, number]> = targetMetadata?.safe_zones || [];
  if (backendSafeZones.length > 0) {
    for (const [szXmin, szYmin, szXmax, szYmax] of backendSafeZones) {
      if (ent.x >= szXmin && ent.x <= szXmax && ent.y >= szYmin && ent.y <= szYmax) {
        return false; // Inside a backend-detected safe zone — skip
      }
    }
  } else {
    // Fallback: legacy hardcoded percentage-based tolerance table exclusion
    const inToleranceTableZone = (pctX >= 0.04 && pctX <= 0.42 && pctY >= 0.70 && pctY <= 1.02);
    if (inToleranceTableZone) return false;
  }

  const defaultRegions = {
    views: { xMin: 0.04, xMax: 0.68, yMin: 0.12, yMax: 0.88 },
    notes: { xMin: 0.04, xMax: 0.38, yMin: 0.18, yMax: 0.62 },
    bom: { xMin: 0.62, xMax: 0.98, yMin: 0.04, yMax: 0.44 },
    title: { xMin: 0.38, xMax: 0.98, yMin: 0.72, yMax: 0.98 },
    titleUpperLeft: { xMin: 0.02, xMax: 0.35, yMin: 0.02, yMax: 0.35 },
    iso: { xMin: 0.62, xMax: 0.98, yMin: 0.42, yMax: 0.74 }
  };
  const regions = targetMetadata?.regions || defaultRegions;
  const inside = (px: number, py: number, box: { xMin: number; xMax: number; yMin: number; yMax: number }) =>
    px >= box.xMin && px <= box.xMax && py >= box.yMin && py <= box.yMax;

  const inViews = inside(pctX, pctY, regions.views);
  const inNotes = inside(pctX, pctY, regions.notes);
  const inBom = inside(pctX, pctY, regions.bom);
  const inIso = inside(pctX, pctY, regions.iso);
  const inTitle = inside(pctX, pctY, regions.title);
  const inTitleUL = inside(pctX, pctY, regions.titleUpperLeft);

  const isTotalQtyText = ["総製作個数", "t. q'ty", "t. qty", "total quantity"].some(x => ent.text.toLowerCase().includes(x));
  if (inTitleUL && isTotalQtyText) return true;

  if (inTitleUL && /^\d+$/.test(ent.text.trim())) return false;

  return inViews || inNotes || inBom || inIso || inTitle;
};

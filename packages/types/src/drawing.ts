export type DrawingFormat = "dxf" | "dwg" | "pdf";

export interface DrawingMetadata {
  title?: string;
  author?: string;
  organization?: string;
  scale?: string;
  units?: string;
  version?: string;
  sheet_number?: string;
}

export interface Drawing {
  id: string;
  filename: string;
  original_filename: string;
  format: DrawingFormat;
  hash: string;
  file_path: string;
  converted_path?: string;
  metadata: DrawingMetadata;
  size_bytes: number;
  upload_date: string;
  entities_extracted: boolean;
}

export interface CadEntity {
  id: string;
  type: "line" | "arc" | "circle" | "text" | "dimension";
  layer: string;
  color?: number;
  coordinates: number[];
  text_value?: string;
  properties?: Record<string, unknown>;
}

export interface CadLayer {
  name: string;
  color?: number;
  is_frozen: boolean;
  is_locked: boolean;
  entity_count: number;
}

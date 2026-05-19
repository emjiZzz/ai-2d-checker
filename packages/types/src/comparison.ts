export type ComparisonStatus = "pending" | "processing" | "completed" | "failed";

export interface BoundingBox {
  min_x: number;
  min_y: number;
  max_x: number;
  max_y: number;
}

export interface ModificationRegion {
  id: string;
  change_type: "added" | "deleted" | "modified";
  bounding_box: BoundingBox;
  confidence: number;
  description?: string;
}

export interface Comparison {
  id: string;
  original_drawing_id: string;
  modified_drawing_id: string;
  status: ComparisonStatus;
  ssim_score: number;
  total_modifications: number;
  regions: ModificationRegion[];
  overlay_image_path: string;
  created_at: string;
  completed_at?: string;
  error_message?: string;
}

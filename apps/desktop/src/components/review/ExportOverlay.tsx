import { LoadingOverlay, Z_INDEX } from "../ui/LoadingOverlay";

export { Z_INDEX };

export function ExportOverlay({ active, phase }: { active: boolean; phase?: string | null }) {
  if (!active) return null;

  return (
    <LoadingOverlay
      active={active}
      title="Exporting PDF Report"
      phase={phase}
    />
  );
}

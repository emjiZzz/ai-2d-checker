import React, { Suspense, lazy } from "react";
import { TwoDWorkspace } from "../../components/review/TwoDWorkspace";

const ThreeDWorkspace = lazy(() => import("../../components/review/ThreeDWorkspace").then(m => ({ default: m.ThreeDWorkspace })));

interface WorkspaceViewProps {
  currentNav: string;
}

export const WorkspaceView: React.FC<WorkspaceViewProps> = ({ currentNav }) => {
  return (
    <div className="flex w-screen h-[calc(100vh-44px)] bg-bg-dark overflow-hidden text-text-primary">
      {currentNav === "workspace" && (
        <TwoDWorkspace currentNav={currentNav} />
      )}

      {currentNav === "3d-workspace" && (
        <Suspense fallback={
          <div className="flex w-full h-full items-center justify-center bg-bg-dark text-text-muted">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent-primary mr-3"></div>
            Loading 3D Engine...
          </div>
        }>
          <ThreeDWorkspace currentNav={currentNav} />
        </Suspense>
      )}
    </div>
  );
};

import { useState, useCallback } from "react";
import { useDrawingStore } from "../stores/drawingStore";

export const useGlobalFileUpload = () => {
  const [isDragging, setIsDragging] = useState(false);
  const { uploadDrawing } = useDrawingStore();

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleFileSelection = useCallback(async (file: File) => {
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!["dwg", "dxf", "step", "stp", "iges", "igs"].includes(ext || "")) {
      alert("Invalid format: Only CAD drawings (.dwg/.dxf) or 3D models (.step/.iges) are supported.");
      return;
    }
    await uploadDrawing(file);
  }, [uploadDrawing]);

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      await handleFileSelection(file);
    }
  }, [handleFileSelection]);

  const handleFileSelectChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      await handleFileSelection(file);
    }
  }, [handleFileSelection]);

  return {
    isDragging,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleFileSelectChange,
    handleFileSelection
  };
};

import { useState, useCallback, useRef } from "react";
import { useDrawingStore } from "../stores/drawingStore";

export const useGlobalFileUpload = () => {
  const [isDragging, setIsDragging] = useState(false);
  const { uploadDrawing } = useDrawingStore();
  const dragCounter = useRef(0);

  const isFileDrag = (e: React.DragEvent) => {
    if (!e.dataTransfer) return false;
    const types = Array.from(e.dataTransfer.types || []);
    return types.includes("Files");
  };

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    if (!isFileDrag(e)) return;
    e.preventDefault();
    dragCounter.current += 1;
    setIsDragging(true);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    if (!isFileDrag(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    if (!isFileDrag(e)) return;
    e.preventDefault();
    dragCounter.current = Math.max(0, dragCounter.current - 1);
    if (dragCounter.current === 0 || !e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragging(false);
      dragCounter.current = 0;
    }
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
    if (!isFileDrag(e)) return;
    e.preventDefault();
    setIsDragging(false);
    dragCounter.current = 0;

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
    handleDragEnter,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleFileSelectChange,
    handleFileSelection
  };
};

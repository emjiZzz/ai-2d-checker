import { useState, useRef } from "react";
import { useAuditStore } from "../../../stores/auditStore";
import { useStandards } from "../../../hooks/useStandards";
import { useClients } from "../../../hooks/useClients";
import { buildHeaders, baseUrl, parseOrThrow } from "../../../services/fetchUtils";

export const useStandardsManager = () => {
  // useStandards() owns server state for the list, delete, and update.
  // uploadStandard stays in useAuditStore: it's an XHR state machine with
  // progress callbacks that TanStack Query cannot model cleanly.
  const {
    standards,
    isLoading: standardsLoading,
    deleteStandard,
    updateStandard,
  } = useStandards();

  const {
    uploadStandard,
    uploadStatus,
    uploadProgress,
    errorMessage,
    resetStore
  } = useAuditStore();

  const {
    clients,
    createClient,
    deleteClient
  } = useClients();

  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [showUploadModal, setShowUploadModal] = useState(false);

  // Scoping context for the upload modal
  const [uploadScope, setUploadScope] = useState<"universal" | "client_specific">("universal");
  const [uploadClient, setUploadClient] = useState<string>("");

  // Directory explorer state
  const [activeClientTab, setActiveClientTab] = useState<string | null>(null);
  const [newClientName, setNewClientName] = useState("");
  const [isAddingClient, setIsAddingClient] = useState(false);

  // Edit modal state
  const [editingStd, setEditingStd] = useState<any | null>(null);
  const [editName, setEditName] = useState("");
  const [editCategory, setEditCategory] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Delete confirmation state
  const [deletingStd, setDeletingStd] = useState<any | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  // Toast notification
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // Vector Chunk Explorer Modal state
  const [explorerStd, setExplorerStd] = useState<any | null>(null);
  const [explorerChunks, setExplorerChunks] = useState<any[]>([]);
  const [explorerLoading, setExplorerLoading] = useState(false);
  const [explorerError, setExplorerError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const showToast = (type: "success" | "error", message: string) => {
    setToast({ type, message });
    setTimeout(() => setToast(null), 3500);
  };

  const openExplorer = async (std: any) => {
    setExplorerStd(std);
    setExplorerChunks([]);
    setExplorerLoading(true);
    setExplorerError(null);

    try {
      const response = await fetch(`${baseUrl()}/api/v1/standards/${std.id}/chunks`, { headers: buildHeaders() });
      const data = await parseOrThrow<any>(response);
      if (data?.success && data?.data) {
        setExplorerChunks(data.data);
      } else {
        setExplorerError(data?.error?.message || "Failed to retrieve standard chunks.");
      }
    } catch (err: any) {
      setExplorerError(err.message || "Network error occurred.");
    } finally {
      setExplorerLoading(false);
    }
  };

  const universalStandards = standards.filter(s => s.scope === "universal" || !s.scope);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => setIsDragOver(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      const file = files[0];
      const ext = file.name.split(".").pop()?.toLowerCase();
      if (ext && ["pdf", "txt", "md", "xlsx", "xls"].includes(ext)) {
        setSelectedFile(file);
        if (!name) setName(file.name.replace(/\.[^/.]+$/, "").replace(/[_\-]/g, " ").toUpperCase());
      } else {
        alert("Unsupported file format! Please upload PDF, TXT, Excel or Markdown.");
      }
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const file = files[0];
      setSelectedFile(file);
      if (!name) setName(file.name.replace(/\.[^/.]+$/, "").replace(/[_\-]/g, " ").toUpperCase());
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile || !name.trim()) return;
    const success = await uploadStandard(
      selectedFile, name,
      category || "General Compliance",
      description || "Engineering drafting compliance parameters.",
      uploadScope, uploadClient
    );
    if (success) {
      setName(""); setCategory(""); setDescription(""); setSelectedFile(null);
      setShowUploadModal(false);
      showToast("success", "Standard ingested successfully.");
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  };

  const triggerUploadModal = (scope: "universal" | "client_specific", clientName = "") => {
    resetStore();
    setUploadScope(scope);
    setUploadClient(clientName);
    setShowUploadModal(true);
  };

  const handleCreateClient = async () => {
    if (newClientName.trim()) {
      try {
        await createClient(newClientName.trim());
        setNewClientName("");
        setIsAddingClient(false);
      } catch {
        showToast("error", "Failed to create client.");
      }
    }
  };

  const openEdit = (std: any) => {
    setEditingStd(std);
    setEditName(std.name);
    setEditCategory(std.category || "");
    setEditDescription(std.description || "");
    setEditError(null);
  };

  const handleEditSave = async () => {
    if (!editingStd || !editName.trim()) return;
    setEditSaving(true);
    setEditError(null);
    try {
      await updateStandard({
        id: editingStd.id,
        name: editName.trim(),
        category: editCategory.trim(),
        description: editDescription.trim(),
      });
      setEditingStd(null);
      showToast("success", "Standard updated successfully.");
    } catch {
      setEditError("Failed to update. Please try again.");
    } finally {
      setEditSaving(false);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deletingStd) return;
    setDeleteLoading(true);
    try {
      await deleteStandard(deletingStd.id);
      showToast("success", `"${deletingStd.name}" has been deleted.`);
    } catch {
      showToast("error", "Failed to delete. Please try again.");
    } finally {
      setDeleteLoading(false);
      setDeletingStd(null);
    }
  };

  return {
    standards, clients, universalStandards,
    standardsLoading,
    deleteClient,
    
    // File upload state
    name, setName,
    category, setCategory,
    description, setDescription,
    selectedFile, setSelectedFile,
    isDragOver, setIsDragOver,
    showUploadModal, setShowUploadModal,
    uploadScope, uploadClient,
    fileInputRef,
    uploadStatus, uploadProgress, errorMessage,
    
    // Directory explorer state
    activeClientTab, setActiveClientTab,
    newClientName, setNewClientName,
    isAddingClient, setIsAddingClient,
    
    // Edit modal state
    editingStd, setEditingStd,
    editName, setEditName,
    editCategory, setEditCategory,
    editDescription, setEditDescription,
    editSaving, editError,
    
    // Delete state
    deletingStd, setDeletingStd,
    deleteLoading,
    
    // Toast
    toast,
    
    // Explorer
    explorerStd, setExplorerStd,
    explorerChunks, explorerLoading, explorerError,
    
    // Handlers
    openExplorer,
    handleDragOver, handleDragLeave, handleDrop, handleFileChange, handleSubmit,
    formatBytes, triggerUploadModal, handleCreateClient,
    openEdit, handleEditSave, handleDeleteConfirm
  };
};

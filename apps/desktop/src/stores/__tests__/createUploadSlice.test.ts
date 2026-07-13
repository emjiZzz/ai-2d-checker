import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useWorkspaceStore } from '../workspaceStore';

// Mock the fetchUtils module because createUploadSlice uses uploadFile
vi.mock('../../services/fetchUtils', () => ({
  uploadFile: vi.fn(),
  baseUrl: vi.fn(() => 'http://localhost'),
  buildHeaders: vi.fn(() => ({})),
  parseOrThrow: vi.fn(),
}));

import { uploadFile } from '../../services/fetchUtils';

describe('createUploadSlice', () => {
  beforeEach(() => {
    // Reset Zustand store state before each test
    useWorkspaceStore.setState({
      oldUploadState: 'idle',
      newUploadState: 'idle',
      uploadQueue: [],
      oldError: null,
      compatibilityStatus: 'Idle',
    });
    vi.clearAllMocks();
  });

  it('rejects files with unsupported extensions', async () => {
    const store = useWorkspaceStore.getState();
    const mockFile = new File(['dummy content'], 'document.txt', { type: 'text/plain' });

    const result = await store.uploadDrawingFile(mockFile, 'old');

    expect(result).toBe(false);
    
    const updatedState = useWorkspaceStore.getState();
    expect(updatedState.oldUploadState).toBe('failed');
    expect(updatedState.oldError).toContain('Unsupported format');
    expect(updatedState.compatibilityStatus).toBe('Unsupported');
    expect(uploadFile).not.toHaveBeenCalled();
  });

  it('rejects files exceeding the maximum size limit', async () => {
    const store = useWorkspaceStore.getState();
    
    // Create a mock file with an overridden size property to simulate > 10GB
    const mockFile = new File([''], 'huge_drawing.dxf');
    Object.defineProperty(mockFile, 'size', { value: 11 * 1024 * 1024 * 1024 });

    const result = await store.uploadDrawingFile(mockFile, 'old');

    expect(result).toBe(false);

    const updatedState = useWorkspaceStore.getState();
    expect(updatedState.oldUploadState).toBe('failed');
    expect(updatedState.oldError).toContain('File exceeds the maximum limit');
  });

  it('rejects executable binaries (MZ header signature)', async () => {
    const store = useWorkspaceStore.getState();
    
    // Create a file whose first two bytes are 0x4D and 0x5A ("MZ")
    const mzHeader = new Uint8Array([0x4D, 0x5A, 0x00, 0x00]);
    const mockExecutable = new File([mzHeader], 'malicious.dxf');

    const result = await store.uploadDrawingFile(mockExecutable, 'old');

    expect(result).toBe(false);

    const updatedState = useWorkspaceStore.getState();
    expect(updatedState.oldUploadState).toBe('failed');
    expect(updatedState.oldError).toContain('Security Violation');
  });

  it('proceeds with upload for valid CAD files', async () => {
    const store = useWorkspaceStore.getState();
    
    // Valid CAD content (no MZ header)
    const validContent = new Uint8Array([0x00, 0x01, 0x02]);
    const mockValid = new File([validContent], 'floorplan.dwg');

    // Mock successful uploadFile response
    (uploadFile as any).mockResolvedValueOnce({
      drawing: { id: 'dwg_123', file_name: 'floorplan.dwg' },
      job: { id: 'job_abc', status: 'processing' }
    });

    const result = await store.uploadDrawingFile(mockValid, 'old');

    expect(result).toBe(true);

    const updatedState = useWorkspaceStore.getState();
    // After returning true, it sets the queue state to processing
    expect(updatedState.oldUploadState).toBe('processing');
    expect(updatedState.activeOldJobId).toBe('job_abc');
    expect(uploadFile).toHaveBeenCalledTimes(1);
    
    // Check if queue has the entry
    const entry = updatedState.uploadQueue.find(q => q.side === 'old');
    expect(entry).toBeDefined();
    expect(entry?.status).toBe('processing');
  });
});

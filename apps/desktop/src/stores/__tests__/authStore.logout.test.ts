import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { useAuthStore } from '../authStore';
import { useConnectionStore } from '../connectionStore';

// Audit finding #3 (revisited from docs/security-remediation-implementation-plan.md,
// Phase A completion log — UserSessionDocument.active was written on login but never
// read/checked anywhere): the backend now exposes POST /auth/logout to revoke the
// current session, and authStore.logout() must actually call it — a purely
// client-side "forget the token" logout leaves the session marked active server-side
// forever (until natural expiry), so the revoked-session check in
// api/dependencies.py::get_current_user has nothing to bite on if this never fires.

describe('authStore.logout', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('{}', { status: 200 }))));
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...window.location, reload: vi.fn() },
    });

    useConnectionStore.setState({ backendUrl: 'http://localhost:8000', apiToken: 'test-api-token' } as any);
    useAuthStore.setState({
      user: { id: '1', username: 'alice', role: 'user', permissions: [], created_at: '' },
      sessionToken: 'session-token-abc',
      isAuthenticated: true,
      isLoading: false,
      isInitializing: false,
      error: null,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('calls POST /auth/logout with the current session token before clearing local state', async () => {
    await useAuthStore.getState().logout();

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/auth/logout',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'X-Session-Token': 'session-token-abc',
          Authorization: 'Bearer test-api-token',
        }),
      })
    );

    const state = useAuthStore.getState();
    expect(state.sessionToken).toBeNull();
    expect(state.isAuthenticated).toBe(false);
  });

  it('still clears local state and does not throw if the server call fails', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('network down'));

    await expect(useAuthStore.getState().logout()).resolves.toBeUndefined();

    const state = useAuthStore.getState();
    expect(state.sessionToken).toBeNull();
    expect(state.isAuthenticated).toBe(false);
  });

  it('does not call the backend if there was no session token to begin with', async () => {
    useAuthStore.setState({ sessionToken: null });

    await useAuthStore.getState().logout();

    expect(fetch).not.toHaveBeenCalled();
  });
});

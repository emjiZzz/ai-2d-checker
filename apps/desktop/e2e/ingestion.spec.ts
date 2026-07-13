import { test, expect } from '@playwright/test';

test.describe('CAD Ingestion Critical Path', () => {
  test('User can login, enter room, and see upload zones', async ({ page }) => {
    // Mock API responses
    const corsHeaders = { 'Access-Control-Allow-Origin': '*' };
    
    // Mock successful login
    await page.route('**/api/v1/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        headers: corsHeaders,
        json: { 
          success: true, 
          data: { 
            session_token: 'fake-token',
            user: { id: 'u1', username: 'TestUser', role: 'user', permissions: ['audit'] }
          }
        }
      });
    });

    // Mock auth/me for subsequent calls
    await page.route('**/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        headers: corsHeaders,
        json: { success: true, data: { id: 'u1', username: 'TestUser', role: 'user', permissions: ['audit'] } }
      });
    });

    // Mock rooms list
    await page.route('**/api/v1/rooms', async (route, request) => {
      if (request.url().endsWith('/api/v1/rooms')) {
        const json = [{ 
          id: 'test-room-1', 
          name: 'E2E Test Room', 
          description: null,
          client_name: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          last_opened_at: null
        }];
        await route.fulfill({ headers: corsHeaders, json });
      } else {
        await route.continue();
      }
    });

    // Mock individual room fetch
    await page.route('**/api/v1/rooms/test-room-1', async (route) => {
      const json = { 
        id: 'test-room-1', 
        name: 'E2E Test Room', 
        description: null,
        client_name: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        last_opened_at: null
      };
      await route.fulfill({ headers: corsHeaders, json });
    });

    // Mock workspace load
    await page.route('**/api/v1/rooms/test-room-1/workspace', async (route) => {
      await route.fulfill({ headers: corsHeaders, json: { old_drawing: null, new_drawing: null, audit_session: null } });
    });

    // 1. Navigate to the app (will show LoginPage because tauri fails to load session)
    await page.goto('/');

    // Wait for the app to finish its initial health check / restore attempt
    await expect(page).toHaveTitle(/KMTI Checker/i);

    // 2. We should see the Login page
    const usernameInput = page.getByLabel(/Username or ID/i).first();
    await expect(usernameInput).toBeVisible({ timeout: 10000 });
    
    // Fill in credentials and submit
    await usernameInput.fill('engineer');
    // Assuming password field exists
    const passwordInput = page.getByLabel(/Security Password/i);
    if (await passwordInput.count() > 0) {
      await passwordInput.fill('engineer123');
    }
    
    await page.getByRole('button', { name: /Initialize Portal Access/i }).click();

    // 3. We are now on RoomsView. Click the mocked room to open it.
    await expect(page.getByText('E2E Test Room')).toBeVisible({ timeout: 10000 });
    await page.getByText('E2E Test Room').click();

    // 4. Verify the Upload Zones are present
    // First ensure we're not stuck on loading state
    await expect(page.getByText(/Loading workspace state/i)).not.toBeVisible({ timeout: 10000 });
    
    // Look for the text that indicates the dropzone is ready
    const dropzoneText = page.locator('p', { hasText: /Drag & drop or/i }).first();
    await expect(dropzoneText).toBeVisible({ timeout: 10000 });
  });
});

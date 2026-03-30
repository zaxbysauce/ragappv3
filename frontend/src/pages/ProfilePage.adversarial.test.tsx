// ADVERSARIAL TESTS for ProfilePage — XSS, password validation, injection, edge cases
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import ProfilePage from '@/pages/ProfilePage';
import { toast } from 'sonner';

// --- Mocks ---
vi.mock('@/stores/useAuthStore', () => ({
  useAuthStore: vi.fn((selector) => {
    const state = {
      user: { id: 1, username: 'testuser', full_name: 'Test User', role: 'member' },
      isAuthenticated: true, isLoading: false,
      updateProfile: vi.fn().mockResolvedValue({}),
    };
    return typeof selector === 'function' ? selector(state) : state;
  }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/components/ui/card', () => ({
  Card: ({ children }: any) => <div data-testid="card">{children}</div>,
  CardContent: ({ children }: any) => <div data-testid="card-content">{children}</div>,
  CardHeader: ({ children }: any) => <div data-testid="card-header">{children}</div>,
  CardTitle: ({ children }: any) => <h3>{children}</h3>,
  CardDescription: ({ children }: any) => <p>{children}</p>,
}));

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, ...props }: any) => <button onClick={onClick} disabled={disabled} {...props}>{children}</button>,
}));

vi.mock('@/components/ui/input', () => ({
  Input: (props: any) => <input {...props} />,
}));

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children }: any) => <span>{children}</span>,
}));

vi.mock('@/components/auth/ProtectedRoute', () => ({
  ProtectedRoute: ({ children }: any) => <div>{children}</div>,
}));

describe('ProfilePage ADVERSARIAL', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(() => { vi.restoreAllMocks(); });

  // 1. XSS in profile name
  describe('XSS in profile name', () => {
    const xssPayloads = [
      '<script>alert("xss")</script>',
      '<img onerror="alert(1)" src=x>',
      '"><script>alert(document.cookie)</script>',
    ];

    it.each(xssPayloads)('should NOT execute XSS when full_name is: %s', async (payload) => {
      const { useAuthStore } = await import('@/stores/useAuthStore');
      vi.mocked(useAuthStore).mockImplementation((selector: any) => {
        const state = {
          user: { id: 1, username: 'testuser', full_name: payload, role: 'member' },
          isAuthenticated: true, isLoading: false,
          updateProfile: vi.fn().mockResolvedValue({}),
        };
        return typeof selector === 'function' ? selector(state) : state;
      });

      await act(async () => { render(<ProfilePage />); });

      // Should render safely
      expect(document.querySelectorAll('script')).toHaveLength(0);
      expect(screen.getByText('Profile')).toBeInTheDocument();
    });
  });

  // 2. Password validation edge cases
  describe('Password validation edge cases', () => {
    it('should reject password shorter than 8 characters (7 chars)', async () => {
      await act(async () => { render(<ProfilePage />); });

      const currentPw = screen.getByLabelText('Current password');
      const newPw = screen.getByLabelText('New password');
      const confirmPw = screen.getByLabelText('Confirm new password');

      await act(async () => {
        fireEvent.change(currentPw, { target: { value: 'oldpass' } });
        fireEvent.change(newPw, { target: { value: '1234567' } }); // 7 chars
        fireEvent.change(confirmPw, { target: { value: '1234567' } });
      });

      const form = newPw.closest('form')!;
      await act(async () => { fireEvent.submit(form); });

      await waitFor(() => {
        expect(screen.getByText('Password must be at least 8 characters long')).toBeInTheDocument();
      });
      expect(toast.success).not.toHaveBeenCalled();
    });

    it('should accept exactly 8 character password', async () => {
      await act(async () => { render(<ProfilePage />); });

      const currentPw = screen.getByLabelText('Current password');
      const newPw = screen.getByLabelText('New password');
      const confirmPw = screen.getByLabelText('Confirm new password');

      await act(async () => {
        fireEvent.change(currentPw, { target: { value: 'oldpass' } });
        fireEvent.change(newPw, { target: { value: '12345678' } }); // exactly 8
        fireEvent.change(confirmPw, { target: { value: '12345678' } });
      });

      const form = newPw.closest('form')!;
      await act(async () => { fireEvent.submit(form); });

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith('Password changed successfully');
      });
    });

    it('should reject mismatched passwords', async () => {
      await act(async () => { render(<ProfilePage />); });

      const currentPw = screen.getByLabelText('Current password');
      const newPw = screen.getByLabelText('New password');
      const confirmPw = screen.getByLabelText('Confirm new password');

      await act(async () => {
        fireEvent.change(currentPw, { target: { value: 'oldpass' } });
        fireEvent.change(newPw, { target: { value: 'newpassword123' } });
        fireEvent.change(confirmPw, { target: { value: 'differentpassword' } });
      });

      const form = newPw.closest('form')!;
      await act(async () => { fireEvent.submit(form); });

      await waitFor(() => {
        expect(screen.getByText('Passwords do not match')).toBeInTheDocument();
      });
      expect(toast.success).not.toHaveBeenCalled();
    });

    it('should reject empty current password', async () => {
      await act(async () => { render(<ProfilePage />); });

      const newPw = screen.getByLabelText('New password');
      const confirmPw = screen.getByLabelText('Confirm new password');

      await act(async () => {
        fireEvent.change(newPw, { target: { value: 'validpassword123' } });
        fireEvent.change(confirmPw, { target: { value: 'validpassword123' } });
      });

      const form = newPw.closest('form')!;
      await act(async () => { fireEvent.submit(form); });

      await waitFor(() => {
        expect(screen.getByText('Current password is required')).toBeInTheDocument();
      });
    });

    it('should reject empty new password', async () => {
      await act(async () => { render(<ProfilePage />); });

      // The Change Password button should be disabled when new password is empty
      const buttons = screen.getAllByRole('button');
      const passwordButton = buttons.find(b => b.textContent?.includes('Change Password'));
      expect(passwordButton).toBeDisabled();
    });
  });

  // 3. API error handling
  describe('API error handling', () => {
    it('should show error toast when profile update fails', async () => {
      const { useAuthStore } = await import('@/stores/useAuthStore');
      vi.mocked(useAuthStore).mockImplementation((selector: any) => {
        const state = {
          user: { id: 1, username: 'testuser', full_name: 'Test User', role: 'member' },
          isAuthenticated: true, isLoading: false,
          updateProfile: vi.fn().mockRejectedValue(new Error('500')),
        };
        return typeof selector === 'function' ? selector(state) : state;
      });

      await act(async () => { render(<ProfilePage />); });

      const fullNameInput = screen.getByLabelText('Full name');
      await act(async () => {
        fireEvent.change(fullNameInput, { target: { value: 'New Name' } });
      });

      const saveBtn = screen.getByRole('button', { name: /save changes/i });
      await act(async () => { fireEvent.click(saveBtn); });

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Failed to update profile');
      });
    });

    it('should show error toast when password change fails', async () => {
      const { useAuthStore } = await import('@/stores/useAuthStore');
      vi.mocked(useAuthStore).mockImplementation((selector: any) => {
        const state = {
          user: { id: 1, username: 'testuser', full_name: 'Test User', role: 'member' },
          isAuthenticated: true, isLoading: false,
          updateProfile: vi.fn().mockRejectedValue(new Error('500')),
        };
        return typeof selector === 'function' ? selector(state) : state;
      });

      await act(async () => { render(<ProfilePage />); });

      const currentPw = screen.getByLabelText('Current password');
      const newPw = screen.getByLabelText('New password');
      const confirmPw = screen.getByLabelText('Confirm new password');

      await act(async () => {
        fireEvent.change(currentPw, { target: { value: 'oldpass' } });
        fireEvent.change(newPw, { target: { value: 'newpassword123' } });
        fireEvent.change(confirmPw, { target: { value: 'newpassword123' } });
      });

      const form = newPw.closest('form')!;
      await act(async () => { fireEvent.submit(form); });

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Failed to change password');
      });
    });
  });

  // 4. Null user handling
  describe('Null user handling', () => {
    it('should show loading state when user is null', async () => {
      const { useAuthStore } = await import('@/stores/useAuthStore');
      vi.mocked(useAuthStore).mockImplementation((selector: any) => {
        const state = { user: null, isAuthenticated: false, isLoading: false, updateProfile: vi.fn() };
        return typeof selector === 'function' ? selector(state) : state;
      });

      await act(async () => { render(<ProfilePage />); });

      expect(screen.getByText('Loading profile')).toBeInTheDocument();
    });
  });

  // 5. Full name edge cases
  describe('Full name edge cases', () => {
    it('should disable save button when name is unchanged', async () => {
      // Ensure we have a valid user (prior test may have re-mocked to null)
      const { useAuthStore } = await import('@/stores/useAuthStore');
      vi.mocked(useAuthStore).mockImplementation((selector: any) => {
        const state = {
          user: { id: 1, username: 'testuser', full_name: 'Test User', role: 'member' },
          isAuthenticated: true, isLoading: false,
          updateProfile: vi.fn().mockResolvedValue({}),
        };
        return typeof selector === 'function' ? selector(state) : state;
      });

      // Default mock has full_name: 'Test User'. Initial fullName state = user.full_name.
      // Button disabled when: fullName === user.full_name (no changes to save)
      await act(async () => { render(<ProfilePage />); });

      // Wait for the profile form to render
      await waitFor(() => {
        expect(screen.getByText('Profile Information')).toBeInTheDocument();
      });

      // The save button should be disabled
      const buttons = screen.getAllByRole('button');
      const saveBtn = buttons.find(b => b.textContent?.includes('Save Changes'));
      expect(saveBtn).toBeDefined();
      expect(saveBtn!.tagName).toBe('BUTTON');
      expect(saveBtn!.hasAttribute('disabled')).toBe(true);
    });

    it('should disable save button when name is empty', async () => {
      const { useAuthStore } = await import('@/stores/useAuthStore');
      vi.mocked(useAuthStore).mockImplementation((selector: any) => {
        const state = {
          user: { id: 1, username: 'testuser', full_name: '', role: 'member' },
          isAuthenticated: true, isLoading: false,
          updateProfile: vi.fn(),
        };
        return typeof selector === 'function' ? selector(state) : state;
      });

      await act(async () => { render(<ProfilePage />); });

      const saveBtn = screen.getByRole('button', { name: /save changes/i });
      expect(saveBtn).toBeDisabled();
    });

    it('should handle very long full name (1000+ chars)', async () => {
      const { useAuthStore } = await import('@/stores/useAuthStore');
      vi.mocked(useAuthStore).mockImplementation((selector: any) => {
        const state = {
          user: { id: 1, username: 'testuser', full_name: 'A'.repeat(2000), role: 'member' },
          isAuthenticated: true, isLoading: false,
          updateProfile: vi.fn(),
        };
        return typeof selector === 'function' ? selector(state) : state;
      });

      await act(async () => { render(<ProfilePage />); });

      expect(screen.getByText('Profile')).toBeInTheDocument();
      const fullNameInput = screen.getByLabelText('Full name') as HTMLInputElement;
      expect(fullNameInput.value.length).toBe(2000);
    });

    it('should handle null full_name', async () => {
      const { useAuthStore } = await import('@/stores/useAuthStore');
      vi.mocked(useAuthStore).mockImplementation((selector: any) => {
        const state = {
          user: { id: 1, username: 'testuser', full_name: null, role: 'member' },
          isAuthenticated: true, isLoading: false,
          updateProfile: vi.fn(),
        };
        return typeof selector === 'function' ? selector(state) : state;
      });

      await act(async () => { render(<ProfilePage />); });

      expect(screen.getByText('Profile')).toBeInTheDocument();
    });
  });

  // 6. Unicode in names
  describe('Unicode handling', () => {
    it('should handle Unicode full names', async () => {
      const { useAuthStore } = await import('@/stores/useAuthStore');
      vi.mocked(useAuthStore).mockImplementation((selector: any) => {
        const state = {
          user: { id: 1, username: 'testuser', full_name: '张三 😀 مرحبا', role: 'member' },
          isAuthenticated: true, isLoading: false,
          updateProfile: vi.fn(),
        };
        return typeof selector === 'function' ? selector(state) : state;
      });

      await act(async () => { render(<ProfilePage />); });

      const fullNameInput = screen.getByLabelText('Full name') as HTMLInputElement;
      expect(fullNameInput.value).toBe('张三 😀 مرحبا');
    });
  });

  // 7. Password fields are masked
  describe('Password field security', () => {
    it('should render all password fields as type=password', async () => {
      await act(async () => { render(<ProfilePage />); });

      expect(screen.getByLabelText('Current password')).toHaveAttribute('type', 'password');
      expect(screen.getByLabelText('New password')).toHaveAttribute('type', 'password');
      expect(screen.getByLabelText('Confirm new password')).toHaveAttribute('type', 'password');
    });
  });

  // 8. Username immutability
  describe('Username immutability', () => {
    it('should have username field disabled', async () => {
      await act(async () => { render(<ProfilePage />); });

      const usernameInput = screen.getByLabelText('Username');
      expect(usernameInput).toBeDisabled();
      expect(usernameInput).toHaveValue('testuser');
    });
  });

  // 9. Password cleared on success
  describe('Password state management', () => {
    it('should clear password fields after successful change', async () => {
      await act(async () => { render(<ProfilePage />); });

      const currentPw = screen.getByLabelText('Current password') as HTMLInputElement;
      const newPw = screen.getByLabelText('New password') as HTMLInputElement;
      const confirmPw = screen.getByLabelText('Confirm new password') as HTMLInputElement;

      await act(async () => {
        fireEvent.change(currentPw, { target: { value: 'oldpass' } });
        fireEvent.change(newPw, { target: { value: 'newpassword123' } });
        fireEvent.change(confirmPw, { target: { value: 'newpassword123' } });
      });

      const form = newPw.closest('form')!;
      await act(async () => { fireEvent.submit(form); });

      await waitFor(() => {
        expect(currentPw.value).toBe('');
        expect(newPw.value).toBe('');
        expect(confirmPw.value).toBe('');
      });
    });
  });
});

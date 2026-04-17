import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { VaultGroupAccessPanel } from '@/components/VaultGroupAccessPanel';

// Mock API
vi.mock('@/lib/api', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

// Mock sonner
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// Mock UI components
vi.mock('@/components/ui/card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <div data-testid="card">{children}</div>,
  CardContent: ({ children }: { children: React.ReactNode }) => <div data-testid="card-content">{children}</div>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <div data-testid="card-header">{children}</div>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <h3>{children}</h3>,
  CardDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
}));

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} {...props}>{children}</button>
  ),
}));

vi.mock('@/components/ui/input', () => ({
  Input: (props: any) => <input {...props} />,
}));

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}));

describe('VaultGroupAccessPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the panel title', async () => {
    const { apiClient } = await import('@/lib/api');
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: { group_access: [], total: 0 } });

    await act(async () => {
      render(<VaultGroupAccessPanel vaultId={1} />);
    });

    expect(screen.getByText('Group Access')).toBeInTheDocument();
  });

  it('renders the description', async () => {
    const { apiClient } = await import('@/lib/api');
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: { group_access: [], total: 0 } });

    await act(async () => {
      render(<VaultGroupAccessPanel vaultId={1} />);
    });

    expect(screen.getByText('Manage organization group access to this vault')).toBeInTheDocument();
  });

  it('shows loading state while fetching', async () => {
    const { apiClient } = await import('@/lib/api');
    (apiClient.get as ReturnType<typeof vi.fn>).mockImplementationOnce(
      () => new Promise(() => {}) // Never resolves to keep loading state
    );

    await act(async () => {
      render(<VaultGroupAccessPanel vaultId={1} />);
    });

    // Loading spinner should be present
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders empty state when no groups have access', async () => {
    const { apiClient } = await import('@/lib/api');
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: { group_access: [], total: 0 } });

    await act(async () => {
      render(<VaultGroupAccessPanel vaultId={1} />);
    });

    await waitFor(() => {
      expect(screen.getByText(/No groups have access yet/i)).toBeInTheDocument();
    });
  });

  it('renders the panel as a Card component', async () => {
    const { apiClient } = await import('@/lib/api');
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: { group_access: [], total: 0 } });

    await act(async () => {
      render(<VaultGroupAccessPanel vaultId={1} />);
    });

    await waitFor(() => {
      expect(document.querySelector('[data-testid="card"]')).toBeInTheDocument();
    });
  });

  it('renders with role=status for accessibility', async () => {
    const { apiClient } = await import('@/lib/api');
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: { group_access: [], total: 0 } });

    await act(async () => {
      render(<VaultGroupAccessPanel vaultId={1} />);
    });

    await waitFor(() => {
      expect(document.querySelector('[role="status"]')).toBeInTheDocument();
    });
  });

  it('renders Users icon', async () => {
    const { apiClient } = await import('@/lib/api');
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: { group_access: [], total: 0 } });

    await act(async () => {
      render(<VaultGroupAccessPanel vaultId={1} />);
    });

    await waitFor(() => {
      const icons = document.querySelectorAll('svg');
      expect(icons.length).toBeGreaterThan(0);
    });
  });

  it('accepts any vaultId without crashing', async () => {
    const { apiClient } = await import('@/lib/api');
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: { group_access: [], total: 0 } });

    await act(async () => {
      render(<VaultGroupAccessPanel vaultId={999} />);
    });

    await waitFor(() => {
      expect(screen.getByText('Group Access')).toBeInTheDocument();
    });
  });

  it('renders identically for different vaultIds', async () => {
    const { apiClient } = await import('@/lib/api');
    let result: ReturnType<typeof render>;
    let rerenderFn: (ui: React.ReactElement) => void;

    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: { group_access: [], total: 0 } });
    await act(async () => {
      const r = render(<VaultGroupAccessPanel vaultId={1} />);
      result = r;
      rerenderFn = r.rerender;
    });

    await waitFor(() => {
      expect(screen.getByText('Group Access')).toBeInTheDocument();
    });

    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: { group_access: [], total: 0 } });
    await act(async () => {
      rerenderFn!(<VaultGroupAccessPanel vaultId={42} />);
    });

    await waitFor(() => {
      expect(screen.getByText('Group Access')).toBeInTheDocument();
    });
  });

  it('renders the Grant button', async () => {
    const { apiClient } = await import('@/lib/api');
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: { group_access: [], total: 0 } });

    await act(async () => {
      render(<VaultGroupAccessPanel vaultId={1} />);
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Grant/i })).toBeInTheDocument();
    });
  });
});

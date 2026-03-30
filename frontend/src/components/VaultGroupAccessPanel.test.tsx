import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { VaultGroupAccessPanel } from '@/components/VaultGroupAccessPanel';

// Mock UI components
vi.mock('@/components/ui/card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <div data-testid="card">{children}</div>,
  CardContent: ({ children }: { children: React.ReactNode }) => <div data-testid="card-content">{children}</div>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <div data-testid="card-header">{children}</div>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <h3>{children}</h3>,
  CardDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
}));

describe('VaultGroupAccessPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the panel title', async () => {
    await act(async () => {
      render(<VaultGroupAccessPanel vaultId={1} />);
    });

    expect(screen.getByText('Group Access')).toBeInTheDocument();
  });

  it('renders the description', async () => {
    await act(async () => {
      render(<VaultGroupAccessPanel vaultId={1} />);
    });

    expect(screen.getByText('Manage organization group access to this vault')).toBeInTheDocument();
  });

  it('renders Coming Soon placeholder', async () => {
    await act(async () => {
      render(<VaultGroupAccessPanel vaultId={1} />);
    });

    expect(screen.getByText('Coming Soon')).toBeInTheDocument();
  });

  it('renders description for the coming soon feature', async () => {
    await act(async () => {
      render(<VaultGroupAccessPanel vaultId={1} />);
    });

    expect(screen.getByText(/group-based vault access management/i)).toBeInTheDocument();
  });

  it('renders the panel as a Card component', async () => {
    await act(async () => {
      render(<VaultGroupAccessPanel vaultId={1} />);
    });

    expect(document.querySelector('[data-testid="card"]')).toBeInTheDocument();
  });

  it('renders with role=status for accessibility', async () => {
    await act(async () => {
      render(<VaultGroupAccessPanel vaultId={1} />);
    });

    expect(document.querySelector('[role="status"]')).toBeInTheDocument();
  });

  it('renders centered content layout', async () => {
    await act(async () => {
      render(<VaultGroupAccessPanel vaultId={1} />);
    });

    // Check that the Coming Soon section has text-center class applied
    const statusElement = document.querySelector('[role="status"]');
    expect(statusElement).toHaveClass('text-center');
  });

  it('renders Users icon', async () => {
    await act(async () => {
      render(<VaultGroupAccessPanel vaultId={1} />);
    });

    // The component uses lucide-react Users icon
    const icons = document.querySelectorAll('svg');
    expect(icons.length).toBeGreaterThan(0);
  });

  it('accepts any vaultId without using it', async () => {
    // This tests that the vaultId is accepted but not used (since it's a placeholder)
    await act(async () => {
      render(<VaultGroupAccessPanel vaultId={999} />);
    });

    expect(screen.getByText('Coming Soon')).toBeInTheDocument();
  });

  it('renders identically for different vaultIds', async () => {
    let rerenderFn: (ui: React.ReactElement) => void;

    await act(async () => {
      const result = render(<VaultGroupAccessPanel vaultId={1} />);
      rerenderFn = result.rerender;
    });

    const firstRender = screen.getByText('Coming Soon');

    await act(async () => {
      rerenderFn(<VaultGroupAccessPanel vaultId={42} />);
    });

    const secondRender = screen.getByText('Coming Soon');
    expect(firstRender).toBe(secondRender);
  });
});
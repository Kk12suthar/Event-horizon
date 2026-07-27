// @vitest-environment jsdom

import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import type { ReactElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppErrorBoundary, RouteErrorBoundary } from './AppErrorBoundary';

function BrokenScreen(): ReactElement {
  throw new Error('Route render failed');
}

function ConditionalScreen() {
  const location = useLocation();
  if (location.pathname === '/broken') throw new Error('Broken route');
  return <div>Safe route</div>;
}

function RouteControls() {
  const navigate = useNavigate();
  return <button onClick={() => navigate('/safe')}>Open safe route</button>;
}

describe('AppErrorBoundary', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('shows a recoverable screen instead of leaving the application blank', () => {
    render(
      <AppErrorBoundary>
        <BrokenScreen />
      </AppErrorBoundary>,
    );

    expect(screen.getByRole('alert')).toBeTruthy();
    expect(screen.getByText('This screen could not be displayed')).toBeTruthy();
    expect(screen.getByText('Route render failed')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Return to Data' }).getAttribute('href')).toBe('/app/project');
  });

  it('resets a route crash when navigation moves to a healthy URL', () => {
    render(
      <MemoryRouter initialEntries={['/broken']}>
        <RouteControls />
        <RouteErrorBoundary>
          <ConditionalScreen />
        </RouteErrorBoundary>
      </MemoryRouter>,
    );

    expect(screen.getByRole('alert')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Open safe route' }));
    expect(screen.getByText('Safe route')).toBeTruthy();
  });
});
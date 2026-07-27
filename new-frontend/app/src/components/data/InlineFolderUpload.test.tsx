// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { InlineFolderUpload } from './InlineFolderUpload';

afterEach(cleanup);

const baseProps = {
  folderName: 'Operations',
  canUpload: true,
  stage: 'idle' as const,
  progress: 0,
  error: null,
  onUpload: vi.fn(async () => undefined),
  onOpen: vi.fn(),
  onClose: vi.fn(),
};

describe('InlineFolderUpload', () => {
  it('stays compact until the selected folder requests upload', () => {
    const onOpen = vi.fn();
    render(<InlineFolderUpload {...baseProps} open={false} onOpen={onOpen} />);

    fireEvent.click(screen.getByRole('button', { name: 'Add source files' }));

    expect(onOpen).toHaveBeenCalledOnce();
    expect(screen.queryByLabelText('Upload files to Operations')).toBeNull();
  });

  it('uploads selected files inside the folder panel', () => {
    const onUpload = vi.fn(async () => undefined);
    const { container } = render(<InlineFolderUpload {...baseProps} open onUpload={onUpload} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['order_id,total\n1,42'], 'orders.csv', { type: 'text/csv' });

    fireEvent.change(input, { target: { files: [file] } });

    expect(onUpload).toHaveBeenCalledWith([file]);
    expect(screen.getByText('Upload into Operations')).toBeTruthy();
  });

  it('shows progress and errors without leaving the canvas', () => {
    render(
      <InlineFolderUpload
        {...baseProps}
        open
        stage="uploading"
        progress={48}
        error="Storage quota reached"
      />,
    );

    expect(screen.getByText('48% complete')).toBeTruthy();
    expect(screen.getByText('Storage quota reached')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Close upload panel' })).toBeTruthy();
  });
});
import { describe, expect, it } from 'vitest';
import viteConfig from '../../vite.config';

describe('production asset paths', () => {
  it('uses root-relative assets so every nested app route can boot directly', () => {
    expect(viteConfig.base).toBe('/');
  });
});
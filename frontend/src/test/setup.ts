import "@testing-library/jest-dom/vitest";

import { afterEach, vi } from "vitest";

// jsdom has no matchMedia; the theme provider asks it for the system preference.
window.matchMedia ??= ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addEventListener: () => {},
  removeEventListener: () => {},
  addListener: () => {},
  removeListener: () => {},
  dispatchEvent: () => false,
})) as unknown as typeof window.matchMedia;

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

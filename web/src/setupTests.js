// Jest setup file — runs before every test suite.
import '@testing-library/jest-dom';

// Ant Design 5 uses window.matchMedia for responsive breakpoints.
// Use a plain function (not jest.fn()) so clearAllMocks() has no effect on it.
window.matchMedia = window.matchMedia || ((query) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
}));

// ResizeObserver stub (antd Table / some components use it)
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

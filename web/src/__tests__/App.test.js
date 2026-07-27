/**
 * Frontend smoke tests.
 * Tests that key pages render without crashing and show basic UI elements.
 * API calls are mocked so no backend is required.
 */

import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

// ---------------------------------------------------------------------------
// Mock external dependencies that can't run in jsdom
// ---------------------------------------------------------------------------

jest.mock('../services/api', () => ({
  get: jest.fn(() => Promise.resolve({ data: {} })),
  post: jest.fn(() => Promise.resolve({ data: {} })),
  put: jest.fn(() => Promise.resolve({ data: {} })),
  delete: jest.fn(() => Promise.resolve({ data: {} })),
  interceptors: {
    request: { use: jest.fn(), eject: jest.fn() },
    response: { use: jest.fn(), eject: jest.fn() },
  },
  defaults: { baseURL: '' },
}));

// antd message module
jest.mock('antd', () => {
  const antd = jest.requireActual('antd');
  return {
    ...antd,
    message: {
      success: jest.fn(),
      error: jest.fn(),
      warning: jest.fn(),
      info: jest.fn(),
    },
  };
});

// socket.io-client (not needed in tests)
jest.mock('socket.io-client', () => ({
  connect: jest.fn(() => ({
    on: jest.fn(),
    off: jest.fn(),
    disconnect: jest.fn(),
    emit: jest.fn(),
  })),
}));

// Canvas API (needed by Chart.js)
HTMLCanvasElement.prototype.getContext = jest.fn(() => ({
  fillRect: jest.fn(), clearRect: jest.fn(),
  getImageData: jest.fn(() => ({ data: [] })), putImageData: jest.fn(),
  createImageData: jest.fn(() => ({})), setTransform: jest.fn(),
  drawImage: jest.fn(), save: jest.fn(), fillText: jest.fn(),
  restore: jest.fn(), beginPath: jest.fn(), moveTo: jest.fn(),
  lineTo: jest.fn(), closePath: jest.fn(), stroke: jest.fn(),
  translate: jest.fn(), scale: jest.fn(), rotate: jest.fn(),
  arc: jest.fn(), fill: jest.fn(), measureText: jest.fn(() => ({ width: 0 })),
  transform: jest.fn(), rect: jest.fn(), clip: jest.fn(),
}));

const api = require('../services/api');

// Convenience wrapper for pages that use react-router hooks
const WithRouter = ({ children }) => <MemoryRouter>{children}</MemoryRouter>;

// ---------------------------------------------------------------------------
// Login page
// ---------------------------------------------------------------------------

describe('Login page', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  test('renders login form', () => {
    const Login = require('../pages/Login').default;
    render(<WithRouter><Login onLoginSuccess={jest.fn()} /></WithRouter>);
    expect(screen.getByRole('button', { name: /sign in|login/i })).toBeInTheDocument();
  });

  test('calls api.post on submit', async () => {
    api.post.mockResolvedValueOnce({
      data: { token: 'test-token', user: { email: 'a@b.com' }, expires_in: 3600 },
    });

    const Login = require('../pages/Login').default;
    const onSuccess = jest.fn();
    render(<WithRouter><Login onLoginSuccess={onSuccess} /></WithRouter>);

    fireEvent.change(screen.getByRole('textbox', { name: /email/i }), {
      target: { value: 'a@b.com' },
    });
    fireEvent.change(document.getElementById('password'), {
      target: { value: 'pass' },
    });
    fireEvent.click(screen.getByRole('button', { name: /sign in|login/i }));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
  });
});

// ---------------------------------------------------------------------------
// NotFound page
// ---------------------------------------------------------------------------

describe('NotFound page', () => {
  test('renders 404 message', () => {
    const NotFound = require('../pages/NotFound').default;
    render(<WithRouter><NotFound /></WithRouter>);
    expect(
      screen.getByText(/404|not found|page does not exist/i)
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Settings page
// ---------------------------------------------------------------------------

describe('Settings page', () => {
  beforeEach(() => {
    localStorage.setItem('authToken', 'fake-token');
    api.get.mockResolvedValue({ data: { settings: {} } });
    api.post.mockResolvedValue({ data: { settings: {} } });
  });

  test('renders without crashing', async () => {
    const Settings = require('../pages/Settings').default;
    render(<WithRouter><Settings /></WithRouter>);
    await waitFor(() => {
      expect(document.body).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// AIEngine page
// ---------------------------------------------------------------------------

describe('AIEngine page', () => {
  beforeEach(() => {
    localStorage.setItem('authToken', 'fake-token');
    api.get.mockResolvedValue({
      data: {
        data: {
          running: false,
          total_processed: 0,
          success_rate: 0,
          avg_score: 0,
          logs: [],
        },
      },
    });
  });

  test('renders without crashing', async () => {
    const AIEngine = require('../pages/AIEngine').default;
    render(<WithRouter><AIEngine /></WithRouter>);
    await waitFor(() => {
      expect(document.body).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// Mock external dependencies that can't run in jsdom
// ---------------------------------------------------------------------------

jest.mock('../services/api', () => ({
  get: jest.fn(() => Promise.resolve({ data: {} })),
  post: jest.fn(() => Promise.resolve({ data: {} })),
  put: jest.fn(() => Promise.resolve({ data: {} })),
  delete: jest.fn(() => Promise.resolve({ data: {} })),
  interceptors: {
    request: { use: jest.fn(), eject: jest.fn() },
    response: { use: jest.fn(), eject: jest.fn() },
  },
  defaults: { baseURL: '' },
}));




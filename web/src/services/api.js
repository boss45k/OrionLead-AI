import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';
const API_TIMEOUT = 120000; // 120 second timeout (web collection can be slow)

const api = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  timeout: API_TIMEOUT,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('authToken');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle responses — redirect to login on 401, but NOT for auth endpoints
// (auth failures like wrong password or Google OAuth errors should propagate to the caller)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const url = error.config?.url || '';
    const isAuthEndpoint = url.includes('/auth/');
    if (error.response?.status === 401 && !isAuthEndpoint) {
      // Clear ALL auth state immediately so in-flight polls stop sending tokens
      localStorage.removeItem('authToken');
      localStorage.removeItem('user');
      localStorage.removeItem('tokenExpiry');
      localStorage.removeItem('userRole');
      // replace() cannot be intercepted by React Router — forces a real page reload
      // so the React tree unmounts and all polling stops before the login page mounts
      window.location.replace('/');
    }
    return Promise.reject(error);
  }
);

/**
 * Extract a human-readable error message from an Axios error.
 * Usage: message.error(extractApiError(err, 'Failed to load X'))
 */
export const extractApiError = (err, fallback = 'Something went wrong') =>
  err?.response?.data?.message ||
  err?.response?.data?.error ||
  err?.message ||
  fallback;

/**
 * Wrapper for API calls - NO mock data fallback for real operations
 * Throws error if API is unavailable
 */
export const apiWithFallback = async (endpoint, method = 'get', data = null, config = {}) => {
  const mergedConfig = { ...config };
  if (method === 'get') {
    return await api.get(endpoint, mergedConfig);
  }
  if (method === 'post') {
    return await api.post(endpoint, data, mergedConfig);
  }
  if (method === 'put') {
    return await api.put(endpoint, data, mergedConfig);
  }
  if (method === 'delete') {
    return await api.delete(endpoint, mergedConfig);
  }
  
  throw new Error(`Unknown method: ${method}`);
};

export const broadcastNotification = (title, description, type = 'info') =>
  apiWithFallback('/notifications/broadcast', 'post', { title, description, type });

export const listBroadcasts = () =>
  apiWithFallback('/notifications/broadcast', 'get');

export const deleteBroadcast = (id) =>
  apiWithFallback(`/notifications/broadcast/${id}`, 'delete');

export const uploadProfilePhoto = (formData) =>
  api.put('/auth/profile/photo', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 30000,
  });

export const deleteProfilePhoto = () => api.delete('/auth/profile/photo');

export default api;

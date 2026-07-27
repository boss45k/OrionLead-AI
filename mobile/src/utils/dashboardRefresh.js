// Lightweight cross-screen signal: any screen can call refreshDashboard()
// and the Dashboard will silently re-fetch its stats.

let _fn = null;

export const setDashboardRefresher = (fn) => { _fn = fn; };
export const clearDashboardRefresher = ()  => { _fn = null; };
export const refreshDashboard       = ()   => { if (_fn) _fn(); };

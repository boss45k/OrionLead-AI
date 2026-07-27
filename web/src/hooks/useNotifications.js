import { useState, useEffect, useCallback, useRef } from 'react';
import { apiWithFallback } from '../services/api';

const STORAGE_KEY = 'nexus_read_notifications';
const POLL_INTERVAL_NORMAL = 30_000;   // 30 s steady state
const POLL_INTERVAL_BURST  =  8_000;   // 8 s right after a new item arrives
const BURST_CYCLES = 2;                // stay fast for 2 extra polls then settle

function getReadIds() {
  try { return new Set(JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')); }
  catch { return new Set(); }
}

function saveReadIds(ids) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...ids]));
}

function formatAgo(isoString) {
  if (!isoString) return null;
  const diff = (Date.now() - new Date(isoString).getTime()) / 1000;
  if (diff < 60)   return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function useNotifications() {
  const [notifications, setNotifications] = useState([]);
  const [readIds, setReadIds]             = useState(getReadIds);
  const [loading, setLoading]             = useState(true);
  const [lastFetch, setLastFetch]         = useState(null);

  const seenIdsRef    = useRef(new Set());
  const burstLeftRef  = useRef(0);
  const timerRef      = useRef(null);

  const fetchNotifications = useCallback(async () => {
    // Stop polling immediately if the user has been logged out
    if (!localStorage.getItem('authToken')) return;
    try {
      const res = await apiWithFallback('/notifications/', 'get');
      const items = (res?.data?.notifications ?? []).map(n => ({
        ...n,
        timeAgo: formatAgo(n.time),
      }));

      // Detect brand-new ids since last fetch
      const incoming = new Set(items.map(n => n.id));
      const isNew = items.some(n => !seenIdsRef.current.has(n.id));
      seenIdsRef.current = incoming;

      if (isNew && seenIdsRef.current.size > 0) {
        burstLeftRef.current = BURST_CYCLES;
      }

      setNotifications(items);
      setLastFetch(new Date());
    } catch {
      // silently keep stale list
    } finally {
      setLoading(false);
    }
  }, []);

  // Polling loop — adjusts interval when burst mode is active
  useEffect(() => {
    let cancelled = false;

    const schedule = () => {
      if (cancelled) return;
      const delay = burstLeftRef.current > 0
        ? (burstLeftRef.current--, POLL_INTERVAL_BURST)
        : POLL_INTERVAL_NORMAL;
      timerRef.current = setTimeout(async () => {
        await fetchNotifications();
        schedule();
      }, delay);
    };

    fetchNotifications().then(schedule);

    return () => {
      cancelled = true;
      clearTimeout(timerRef.current);
    };
  }, [fetchNotifications]);

  const markRead = useCallback((id) => {
    setReadIds(prev => {
      const next = new Set(prev);
      next.add(id);
      saveReadIds(next);
      return next;
    });
  }, []);

  const markAllRead = useCallback((items) => {
    setReadIds(prev => {
      const next = new Set(prev);
      items.forEach(n => next.add(n.id));
      saveReadIds(next);
      return next;
    });
  }, []);

  // Expose a manual refresh so Header can trigger after a lead action
  const refresh = useCallback(() => {
    clearTimeout(timerRef.current);
    burstLeftRef.current = BURST_CYCLES;
    fetchNotifications();
  }, [fetchNotifications]);

  const unreadCount = notifications.filter(n => !readIds.has(n.id)).length;

  return { notifications, readIds, unreadCount, loading, lastFetch, markRead, markAllRead, refresh };
}

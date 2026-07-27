/**
 * useRealtime — React hook for Supabase real-time lead subscriptions.
 *
 * Subscribes to INSERT / UPDATE / DELETE events on leads_cache.
 * Components using this hook get instant UI updates when any device
 * (web or mobile) modifies a lead.
 *
 * Usage:
 *   const { leads, isConnected, error } = useRealtime();
 *
 * Or alongside a local list to merge real-time patches:
 *   useRealtimePatch(setLeads);
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { AppState } from 'react-native';
import { supabase } from '../config/supabase';
import { supabaseLeads } from '../services/supabaseService';
import { flushOfflineQueue } from '../services/syncService';

const TAG = '[useRealtime]';

// ─── useRealtime ──────────────────────────────────────────────────────────────

/**
 * Subscribe to all leads_cache changes.
 * Returns the full current list, auto-updating on every event.
 *
 * @param {object} options
 * @param {number} [options.initialLimit=50]  How many leads to load initially
 */
export function useRealtime({ initialLimit = 50 } = {}) {
  const [leads, setLeads]           = useState([]);
  const [isConnected, setConnected] = useState(false);
  const [error, setError]           = useState(null);
  const channelRef                  = useRef(null);

  const loadInitial = useCallback(async () => {
    try {
      const { data, error: err } = await supabaseLeads.getLeads({ perPage: initialLimit });
      if (err) throw err;
      setLeads(data || []);
    } catch (err) {
      setError(err.message);
    }
  }, [initialLimit]);

  const reconnectTimerRef = useRef(null);

  const subscribe = useCallback(() => {
    // Always clean up any existing channel before creating a new one
    // to prevent duplicate subscriptions on re-renders or foreground transitions.
    if (channelRef.current) {
      supabase.removeChannel(channelRef.current);
      channelRef.current = null;
    }

    channelRef.current = supabase
      .channel('leads_realtime')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'leads_cache' },
        (payload) => {
          const { eventType, new: newRow, old: oldRow } = payload;
          if (__DEV__) console.log(TAG, `Event: ${eventType}`, newRow?.id || oldRow?.id);

          setLeads((prev) => {
            switch (eventType) {
              case 'INSERT':
                // Prevent duplicates
                if (prev.some((l) => l.id === newRow.id)) return prev;
                return [newRow, ...prev];

              case 'UPDATE':
                return prev.map((l) => (l.id === newRow.id ? { ...l, ...newRow } : l));

              case 'DELETE':
                return prev.filter((l) => l.id !== oldRow.id);

              default:
                return prev;
            }
          });
        },
      )
      .subscribe((status) => {
        setConnected(status === 'SUBSCRIBED');
        if (__DEV__) console.log(TAG, 'Channel status:', status);

        if (status === 'CHANNEL_ERROR') {
          setError('Real-time channel error — reconnecting…');
          console.warn(TAG, 'Channel error, scheduling reconnect in 5s');
          // Auto-reconnect after 5 seconds
          clearTimeout(reconnectTimerRef.current);
          reconnectTimerRef.current = setTimeout(() => {
            setError(null);
            subscribe();
          }, 5000);
        } else if (status === 'SUBSCRIBED') {
          // Clear any pending error once successfully reconnected
          setError(null);
        }
      });
  }, []);

  const unsubscribe = useCallback(() => {
    if (channelRef.current) {
      supabase.removeChannel(channelRef.current);
      channelRef.current = null;
      setConnected(false);
    }
  }, []);

  // Handle app foreground/background to manage subscription lifecycle
  useEffect(() => {
    loadInitial();
    subscribe();

    const appStateSub = AppState.addEventListener('change', (state) => {
      if (state === 'active') {
        subscribe();
        loadInitial();  // refresh on foreground
      } else {
        unsubscribe();  // save resources in background
      }
    });

    return () => {
      clearTimeout(reconnectTimerRef.current);
      unsubscribe();
      appStateSub.remove();
    };
  }, []);

  return { leads, setLeads, isConnected, error };
}


// ─── useRealtimePatch ─────────────────────────────────────────────────────────

/**
 * Lightweight variant — patches an external state setter instead of owning
 * the leads array. Use when a screen already has its own leads state.
 *
 * @param {Function} setLeads  setState from the parent component
 * @returns {{ isConnected, error }}
 */
export function useRealtimePatch(setLeads) {
  const [isConnected, setConnected] = useState(false);
  const [error, setError]           = useState(null);
  const channelRef                  = useRef(null);
  const reconnectTimerRef           = useRef(null);
  const mountedRef                  = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    const subscribe = () => {
      if (channelRef.current) {
        supabase.removeChannel(channelRef.current);
        channelRef.current = null;
      }

      channelRef.current = supabase
        .channel('leads_patch')
        .on(
          'postgres_changes',
          { event: '*', schema: 'public', table: 'leads_cache' },
          ({ eventType, new: newRow, old: oldRow }) => {
            setLeads((prev) => {
              if (!Array.isArray(prev)) return prev;
              switch (eventType) {
                case 'INSERT':
                  if (prev.some((l) => l.id === newRow.id)) return prev;
                  return [newRow, ...prev];
                case 'UPDATE':
                  return prev.map((l) => (l.id === newRow.id ? { ...l, ...newRow } : l));
                case 'DELETE':
                  return prev.filter((l) => l.id !== oldRow.id);
                default:
                  return prev;
              }
            });
          },
        )
        .subscribe((status) => {
          if (!mountedRef.current) return;
          setConnected(status === 'SUBSCRIBED');
          if (status === 'CHANNEL_ERROR') {
            console.warn(TAG, 'useRealtimePatch channel error — reconnecting in 5s');
            setError('Channel error');
            clearTimeout(reconnectTimerRef.current);
            reconnectTimerRef.current = setTimeout(() => {
              if (mountedRef.current) { setError(null); subscribe(); }
            }, 5000);
          } else if (status === 'SUBSCRIBED') {
            setError(null);
          }
        });
    };

    subscribe();

    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectTimerRef.current);
      if (channelRef.current) {
        supabase.removeChannel(channelRef.current);
        channelRef.current = null;
      }
    };
  }, [setLeads]);

  return { isConnected, error };
}


// ─── useNetworkSync ───────────────────────────────────────────────────────────

/**
 * Monitor connectivity and flush the offline queue when the app comes online.
 * Import and call this once in your root navigator or App.js.
 */
export function useNetworkSync() {
  useEffect(() => {
    const sub = AppState.addEventListener('change', async (state) => {
      if (state === 'active') {
        const result = await flushOfflineQueue();
        if (result.processed > 0) {
          if (__DEV__) console.log(TAG, `Flushed ${result.processed} offline actions on foreground`);
        }
      }
    });
    // Also attempt a flush immediately on mount
    flushOfflineQueue().catch((err) => {
      console.warn(TAG, 'Initial offline queue flush failed:', err?.message);
    });
    return () => sub.remove();
  }, []);
}

import React, { createContext, useContext, useState, useEffect } from 'react';
import * as SecureStore from 'expo-secure-store';

export const COLORS = {
  // Brand
  primary:      '#6366f1',
  primaryLight: '#818cf8',
  cyan:         '#06b6d4',
  green:        '#22c55e',
  amber:        '#f59e0b',
  red:          '#ef4444',
  purple:       '#8b5cf6',
  orange:       '#f97316',
  teal:         '#14b8a6',
  pink:         '#ec4899',

  // Status
  hot:       '#22c55e',
  warm:      '#f59e0b',
  cold:      '#3b82f6',
  pending:   '#94a3b8',
  qualified: '#6366f1',
  contacted: '#06b6d4',
  converted: '#22c55e',

  // Chart palette
  chart: ['#6366f1', '#06b6d4', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#14b8a6', '#f97316'],
};

const light = {
  bg:           '#f4f6fb',
  card:         '#ffffff',
  cardBorder:   '#e4e9f2',
  surface:      '#eef1fb',
  text:         '#0f172a',
  textSecondary:'#475569',
  textMuted:    '#94a3b8',
  input:        '#f1f4fb',
  inputBorder:  '#dde3ee',
  chip:         '#eef1fb',
  tabBar:       '#ffffff',
  tabBorder:    '#e4e9f2',
  statusBar:    'dark',
};

const dark = {
  bg:           '#080d1a',
  card:         '#0f1829',
  cardBorder:   'rgba(99,102,241,0.15)',
  surface:      '#162033',
  text:         '#e8ecf4',
  textSecondary:'#8895aa',
  textMuted:    '#4a5570',
  input:        '#111c2e',
  inputBorder:  '#1e2d45',
  chip:         '#111c2e',
  tabBar:       '#0c1626',
  tabBorder:    'rgba(99,102,241,0.18)',
  statusBar:    'light',
};

const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    SecureStore.getItemAsync('theme').then((val) => {
      if (val === 'dark') setIsDark(true);
    });
  }, []);

  const toggleTheme = async () => {
    const next = !isDark;
    setIsDark(next);
    await SecureStore.setItemAsync('theme', next ? 'dark' : 'light');
  };

  const theme = isDark ? dark : light;

  return (
    <ThemeContext.Provider value={{ isDark, toggleTheme, theme, colors: COLORS }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}

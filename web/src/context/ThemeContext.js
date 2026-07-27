import { createContext } from 'react';

export const ThemeContext = createContext({
  isDark: true,
  setIsDark: () => {},
});

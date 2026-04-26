import { create } from "zustand";

interface UIState {
  selectedProvider: string | null;
  setSelectedProvider: (name: string | null) => void;
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  selectedProvider: null,
  setSelectedProvider: (name) => set({ selectedProvider: name }),
  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
}));

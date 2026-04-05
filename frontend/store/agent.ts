import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AgentStore {
  language: "en" | "hi";
  setLanguage: (lang: "en" | "hi") => void;
  activeWizardStep: number;
  setWizardStep: (step: number) => void;
}

export const useAgentStore = create<AgentStore>()(
  persist(
    (set) => ({
      language: "en",
      setLanguage: (language) => set({ language }),
      activeWizardStep: 0,
      setWizardStep: (activeWizardStep) => set({ activeWizardStep }),
    }),
    {
      name: "bima360-agent",
      partialize: (state) => ({ language: state.language }),
    }
  )
);

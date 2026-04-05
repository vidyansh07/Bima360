import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthSession {
  accessToken: string;
  idToken: string;
  refreshToken: string;
  expiresAt: number; // epoch ms
}

interface AuthStore {
  session: AuthSession | null;
  agentId: string | null;
  agentName: string | null;
  setSession: (session: AuthSession, agentId: string, agentName: string) => void;
  clearSession: () => void;
  isAuthenticated: () => boolean;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      session: null,
      agentId: null,
      agentName: null,
      setSession: (session, agentId, agentName) =>
        set({ session, agentId, agentName }),
      clearSession: () =>
        set({ session: null, agentId: null, agentName: null }),
      isAuthenticated: () => {
        const s = get().session;
        return s !== null && s.expiresAt > Date.now();
      },
    }),
    {
      name: "bima360-auth",
    }
  )
);

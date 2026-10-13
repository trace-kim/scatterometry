// Which run and sweep the result panels show. Kept for the browser tab's lifetime
// (sessionStorage): results live in the server's memory, so a reload can reattach.
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

interface SessionState {
  runId: string | null;
  sweepId: string | null;
  crosscheck: boolean;
  setRun: (id: string | null) => void;
  setSweep: (id: string | null) => void;
  setCrosscheck: (value: boolean) => void;
}

export const useSession = create<SessionState>()(
  persist(
    (set) => ({
      runId: null,
      sweepId: null,
      crosscheck: false,
      setRun: (runId) => set({ runId }),
      setSweep: (sweepId) => set({ sweepId }),
      setCrosscheck: (crosscheck) => set({ crosscheck }),
    }),
    { name: "masksim.session.v1", storage: createJSONStorage(() => sessionStorage) },
  ),
);

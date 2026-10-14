// Which run, sweep, and uploaded measurement the panels show. Kept for the browser tab's lifetime
// (sessionStorage): results live in the server's memory, so a reload can reattach.
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

interface SessionState {
  runId: string | null;
  sweepId: string | null;
  measurementId: string | null;
  crosscheck: boolean;
  setRun: (id: string | null) => void;
  setSweep: (id: string | null) => void;
  setMeasurement: (id: string | null) => void;
  setCrosscheck: (value: boolean) => void;
}

export const useSession = create<SessionState>()(
  persist(
    (set) => ({
      runId: null,
      sweepId: null,
      measurementId: null,
      crosscheck: false,
      setRun: (runId) => set({ runId }),
      setSweep: (sweepId) => set({ sweepId }),
      setMeasurement: (measurementId) => set({ measurementId }),
      setCrosscheck: (crosscheck) => set({ crosscheck }),
    }),
    { name: "masksim.session.v1", storage: createJSONStorage(() => sessionStorage) },
  ),
);

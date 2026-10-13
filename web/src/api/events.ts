// Live job updates over Server-Sent Events (/api/events) into the query cache.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { FINISHED } from "./hooks";
import type { JobInfo } from "./model";

export function useServerEvents(): boolean {
  const client = useQueryClient();
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const source = new EventSource("/api/events");
    const setJob = (job: JobInfo) => {
      client.setQueryData(["job", job.id], job);
      // Progress events come ~10x/s; sweep records refresh on their own event and at the end.
      if (job.kind === "sweep" && FINISHED.has(job.status)) client.invalidateQueries({ queryKey: ["sweep", job.id] });
    };
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false); // EventSource reconnects by itself
    source.addEventListener("snapshot", (event) => {
      for (const job of JSON.parse(event.data).jobs as JobInfo[]) setJob(job);
    });
    source.addEventListener("job", (event) => setJob(JSON.parse(event.data).job));
    source.addEventListener("sweep-records", (event) => {
      client.invalidateQueries({ queryKey: ["sweep", JSON.parse(event.data).job_id] });
    });
    return () => source.close();
  }, [client]);

  return connected;
}

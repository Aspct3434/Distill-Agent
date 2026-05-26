import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, RefreshCw, ShieldCheck, Workflow } from "lucide-react";
import { api, type SessionMatch, type TaskGraphSnapshot, type TaskGraphVerification } from "../lib/api";

const STATUS_TONE: Record<string, string> = {
  pending: "bg-zinc-700/50 text-zinc-300",
  ready: "bg-sky-500/15 text-sky-300",
  in_progress: "bg-violet-500/20 text-violet-200",
  done: "bg-emerald-500/15 text-emerald-300",
  failed: "bg-red-500/15 text-red-300",
  blocked: "bg-amber-500/15 text-amber-300",
};

function uniqueSessions(matches: SessionMatch[]): string[] {
  return Array.from(new Set(matches.map((match) => match.session_id))).slice(0, 12);
}

function ProofSummary({ verifier }: { verifier: TaskGraphVerification }) {
  const issues = verifier.invalid_evidence_refs.length + verifier.missing_nodes.length + verifier.blocked_nodes.length;
  return (
    <div className="grid gap-3 sm:grid-cols-4">
      <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-3">
        <div className="text-xs uppercase tracking-wide text-zinc-500">Proof</div>
        <div className={`mt-1 flex items-center gap-2 text-sm ${verifier.passed ? "text-emerald-300" : "text-amber-300"}`}>
          {verifier.passed ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
          {verifier.passed ? "passed" : "open"}
        </div>
      </div>
      <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-3">
        <div className="text-xs uppercase tracking-wide text-zinc-500">Missing</div>
        <div className="mt-1 text-2xl font-semibold text-zinc-100">{verifier.missing_nodes.length}</div>
      </div>
      <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-3">
        <div className="text-xs uppercase tracking-wide text-zinc-500">Bad refs</div>
        <div className="mt-1 text-2xl font-semibold text-zinc-100">{verifier.invalid_evidence_refs.length}</div>
      </div>
      <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-3">
        <div className="text-xs uppercase tracking-wide text-zinc-500">Issues</div>
        <div className="mt-1 text-2xl font-semibold text-zinc-100">{issues}</div>
      </div>
    </div>
  );
}

export function TaskGraphPanel() {
  const [sessions, setSessions] = useState<string[]>([]);
  const [sessionId, setSessionId] = useState("");
  const [snapshot, setSnapshot] = useState<TaskGraphSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadSessions = useCallback(async () => {
    const recent = await api.get<SessionMatch[]>("/api/sessions/recent?limit=40");
    const ids = uniqueSessions(recent);
    setSessions(ids);
    setSessionId((current) => current || ids[0] || "");
    return ids;
  }, []);

  const loadGraph = useCallback(
    async (target = sessionId) => {
      if (!target) {
        setSnapshot(null);
        return;
      }
      try {
        const data = await api.get<TaskGraphSnapshot>(`/api/task-graph/${encodeURIComponent(target)}`);
        setSnapshot(data);
        setError(null);
      } catch (e) {
        setSnapshot(null);
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [sessionId],
  );

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      const ids = await loadSessions();
      await loadGraph(sessionId || ids[0] || "");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [loadGraph, loadSessions, sessionId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional fetch-on-mount
    void refresh();
  }, [refresh]);

  async function verify() {
    if (!sessionId) return;
    setBusy(true);
    try {
      const verifier = await api.post<TaskGraphVerification>(
        `/api/task-graph/${encodeURIComponent(sessionId)}/verify`,
      );
      setSnapshot((current) => (current ? { ...current, verifier } : current));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const activeId = snapshot?.active_node?.id ?? "";
  const proofRows = useMemo(() => snapshot?.verifier.proof_report ?? [], [snapshot]);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Workflow className="text-violet-400" size={20} />
        <h2 className="text-lg font-semibold text-zinc-100">Task Graph</h2>
        <select
          value={sessionId}
          onChange={(event) => {
            setSessionId(event.target.value);
            void loadGraph(event.target.value);
          }}
          className="min-w-0 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-200 outline-none focus:border-violet-500"
        >
          <option value="">No session</option>
          {sessions.map((id) => (
            <option key={id} value={id}>
              {id}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => void refresh()}
          disabled={busy}
          className="ml-auto flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:border-violet-600 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          <RefreshCw size={13} /> Refresh
        </button>
        <button
          type="button"
          onClick={() => void verify()}
          disabled={busy || !sessionId}
          className="flex items-center gap-1.5 rounded-lg border border-violet-700 bg-violet-700/20 px-3 py-1.5 text-xs text-violet-100 hover:bg-violet-700/30 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <ShieldCheck size={13} /> Verify
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-950/20 px-3 py-2 text-sm text-amber-200">
          {error}
        </div>
      )}

      {!snapshot || !snapshot.has_graph ? (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-8 text-center text-sm text-zinc-500">
          No task graph is available for this session yet.
        </div>
      ) : (
        <>
          <ProofSummary verifier={snapshot.verifier} />

          <div className="grid min-h-[420px] gap-3 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900">
              <div className="border-b border-zinc-800 px-4 py-3 text-xs text-zinc-500">
                {snapshot.source} graph - {snapshot.summary?.done ?? 0} done / {snapshot.summary?.total ?? snapshot.nodes.length} nodes
              </div>
              <div className="divide-y divide-zinc-800">
                {snapshot.nodes.map((node) => (
                  <div
                    key={node.id}
                    className={`grid gap-2 px-4 py-3 ${node.id === activeId ? "bg-violet-950/20" : ""}`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-sm text-zinc-100">{node.id}</span>
                      <span className={`rounded-full px-2 py-0.5 text-[11px] ${STATUS_TONE[node.status]}`}>
                        {node.status.replace("_", " ")}
                      </span>
                      <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">
                        {node.kind}
                      </span>
                    </div>
                    <div className="text-sm text-zinc-300">{node.title}</div>
                    <div className="grid gap-1 font-mono text-[11px] text-zinc-600 sm:grid-cols-3">
                      <span>deps: {node.depends_on.join(", ") || "none"}</span>
                      <span>proof: {node.proof_requirements.join(", ") || "none"}</span>
                      <span>refs: {node.evidence_refs.join(", ") || "none"}</span>
                    </div>
                    {node.failure_reason && (
                      <div className="text-xs text-amber-300">{node.failure_reason}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <aside className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
              <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">Proof Report</div>
              <div className="mt-3 flex flex-col gap-2">
                {proofRows.length === 0 ? (
                  <div className="text-sm text-zinc-500">No verifier rows yet.</div>
                ) : (
                  proofRows.map((row, index) => {
                    const nodeId = typeof row.node_id === "string" ? row.node_id : `row_${index}`;
                    const passed = Boolean(row.passed);
                    return (
                      <div key={`${nodeId}-${index}`} className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
                        <div className="flex items-center gap-2">
                          <span className={`inline-block size-1.5 rounded-full ${passed ? "bg-emerald-400" : "bg-amber-400"}`} />
                          <span className="font-mono text-xs text-zinc-200">{nodeId}</span>
                        </div>
                        <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap text-[11px] text-zinc-500">
                          {JSON.stringify(row, null, 2)}
                        </pre>
                      </div>
                    );
                  })
                )}
              </div>
            </aside>
          </div>
        </>
      )}
    </div>
  );
}

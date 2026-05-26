import { useCallback, useEffect, useState } from "react";
import { GitBranch, RefreshCw, RotateCcw, ShieldCheck, Zap } from "lucide-react";
import { api, type EvolutionCandidate, type EvolutionStatus } from "../lib/api";

const STATUS_TONE: Record<string, string> = {
  staged: "bg-amber-500/15 text-amber-300",
  promoted: "bg-emerald-500/15 text-emerald-300",
  rejected: "bg-red-500/15 text-red-300",
  rolled_back: "bg-zinc-700/40 text-zinc-400",
};

function fmtDate(value: string | null): string {
  if (!value) return "never";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function shortHash(value: unknown): string {
  return typeof value === "string" && value ? value.slice(0, 10) : "none";
}

export function EvolutionPanel() {
  const [status, setStatus] = useState<EvolutionStatus | null>(null);
  const [candidates, setCandidates] = useState<EvolutionCandidate[]>([]);
  const [selected, setSelected] = useState<EvolutionCandidate | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, c] = await Promise.all([
        api.get<EvolutionStatus>("/api/evolution/status"),
        api.get<EvolutionCandidate[]>("/api/evolution/candidates"),
      ]);
      setStatus(s);
      setCandidates(c);
      setSelected((current) =>
        current ? c.find((candidate) => candidate.candidate_id === current.candidate_id) ?? null : null,
      );
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional fetch-on-mount
    void load();
  }, [load]);

  async function runCycle() {
    setBusy(true);
    try {
      await api.post("/api/evolution/run", { limit: 5 });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function rollback(candidateId: string) {
    setBusy(true);
    try {
      await api.post(`/api/evolution/candidates/${encodeURIComponent(candidateId)}/rollback`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <div className="flex items-center gap-3">
        <ShieldCheck className="text-violet-400" size={20} />
        <h2 className="text-lg font-semibold text-zinc-100">Evolution</h2>
        <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400">
          {status?.verifier_version ?? "proof-carrying"}
        </span>
        <button
          type="button"
          onClick={() => void load()}
          className="ml-auto flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:border-violet-600 hover:text-white"
        >
          <RefreshCw size={13} /> Refresh
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void runCycle()}
          className="flex items-center gap-1.5 rounded-lg border border-violet-700 bg-violet-700/20 px-3 py-1.5 text-xs text-violet-100 hover:bg-violet-700/30 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Zap size={13} /> Run cycle
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/40 bg-red-950/30 px-3 py-2 text-sm text-red-200">
          {error}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-4">
        {(["staged", "promoted", "rejected", "rolled_back"] as const).map((key) => (
          <div key={key} className="rounded-lg border border-zinc-800 bg-zinc-900 p-3">
            <div className="text-xs uppercase tracking-wide text-zinc-500">{key.replace("_", " ")}</div>
            <div className="mt-1 text-2xl font-semibold text-zinc-100">
              {status?.candidates[key] ?? 0}
            </div>
          </div>
        ))}
      </div>

      <div className="grid min-h-[420px] gap-3 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900">
          {candidates.length === 0 ? (
            <div className="py-12 text-center text-sm text-zinc-500">
              No evolution candidates yet.
            </div>
          ) : (
            <div className="divide-y divide-zinc-800">
              {candidates.map((candidate) => (
                <button
                  key={candidate.candidate_id}
                  type="button"
                  onClick={() => setSelected(candidate)}
                  className={`grid w-full grid-cols-[minmax(0,1fr)_auto] gap-3 px-4 py-3 text-left hover:bg-zinc-800/60 ${
                    selected?.candidate_id === candidate.candidate_id ? "bg-zinc-800" : ""
                  }`}
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <GitBranch size={14} className="text-violet-400" />
                      <span className="truncate font-mono text-sm text-zinc-100">{candidate.name}</span>
                      <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">
                        {candidate.kind}
                      </span>
                    </div>
                    <div className="mt-1 truncate font-mono text-[11px] text-zinc-600">
                      {candidate.candidate_id}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <span className={`rounded-full px-2 py-0.5 text-[11px] ${STATUS_TONE[candidate.status]}`}>
                      {candidate.status.replace("_", " ")}
                    </span>
                    <span className="text-[11px] text-zinc-500">{fmtDate(candidate.created_at)}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <aside className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
          {!selected ? (
            <div className="text-sm text-zinc-500">Select a candidate to inspect its proof.</div>
          ) : (
            <div className="flex flex-col gap-3">
              <div>
                <div className="font-mono text-sm text-zinc-100">{selected.name}</div>
                <div className="mt-1 text-xs text-zinc-500">{selected.kind}</div>
              </div>

              <div className="grid gap-2 text-xs">
                <div className="flex justify-between gap-3">
                  <span className="text-zinc-500">Candidate hash</span>
                  <span className="font-mono text-zinc-300">
                    {shortHash(selected.payload.code_hash ?? selected.payload.content_hash)}
                  </span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-zinc-500">Baseline</span>
                  <span className="font-mono text-zinc-300">{shortHash(selected.baseline.hash)}</span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-zinc-500">Score delta</span>
                  <span className="font-mono text-zinc-300">
                    {typeof selected.proof.score_delta === "number"
                      ? selected.proof.score_delta.toFixed(2)
                      : "pending"}
                  </span>
                </div>
              </div>

              {selected.rejection_reason && (
                <div className="rounded-lg border border-red-500/30 bg-red-950/20 p-2 text-xs text-red-200">
                  {selected.rejection_reason}
                </div>
              )}

              <div className="flex flex-col gap-1">
                <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">Verifier checks</div>
                <div className="flex flex-col gap-1">
                  {(selected.proof.checks ?? []).length === 0 ? (
                    <div className="text-xs text-zinc-600">Pending verification.</div>
                  ) : (
                    selected.proof.checks?.map((check) => (
                      <div key={check.name} className="flex items-center gap-2 text-xs">
                        <span
                          className={`inline-block size-1.5 rounded-full ${
                            check.passed ? "bg-emerald-400" : "bg-red-400"
                          }`}
                        />
                        <span className={check.passed ? "text-zinc-300" : "text-red-300"}>
                          {check.name.replaceAll("_", " ")}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {selected.status === "promoted" && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void rollback(selected.candidate_id)}
                  className="mt-auto flex items-center justify-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:border-red-500/50 hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <RotateCcw size={13} /> Roll back
                </button>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

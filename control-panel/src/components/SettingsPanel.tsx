import { useCallback, useEffect, useState } from "react";
import { Cpu, RefreshCw, Save, Trash2, User } from "lucide-react";
import { api, type ModelConfig } from "../lib/api";

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) return value.map(String).join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function KeyValues({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(([, v]) => renderValue(v) !== "—" && renderValue(v) !== "");
  if (entries.length === 0) {
    return <p className="text-sm text-zinc-500">Nothing recorded yet.</p>;
  }
  return (
    <dl className="grid gap-2 sm:grid-cols-2">
      {entries.map(([key, value]) => (
        <div key={key} className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2">
          <dt className="text-[11px] uppercase tracking-wide text-zinc-500">{key}</dt>
          <dd className="mt-0.5 break-words text-sm text-zinc-200">{renderValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function SettingsPanel() {
  const [model, setModel] = useState<ModelConfig>({ model: "", fast_model: "", strong_model: "" });
  const [persona, setPersona] = useState<Record<string, unknown>>({});
  const [profile, setProfile] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    try {
      const [m, p, pr] = await Promise.all([
        api.get<ModelConfig>("/api/config/model"),
        api.get<Record<string, unknown>>("/api/persona").catch(() => ({})),
        api.get<Record<string, unknown>>("/api/profile").catch(() => ({})),
      ]);
      setModel(m);
      setPersona(p);
      setProfile(pr);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional fetch-on-mount
    void load();
  }, [load]);

  async function saveModel(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaved(false);
    try {
      const updated = await api.post<ModelConfig & { updated: boolean }>("/api/config/model", model);
      setModel({
        model: updated.model,
        fast_model: updated.fast_model,
        strong_model: updated.strong_model,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function clearProfile() {
    try {
      await api.del("/api/profile");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const field = (key: keyof ModelConfig, label: string) => (
    <label className="flex flex-col gap-1 text-xs text-zinc-400">
      {label}
      <input
        value={model[key]}
        onChange={(e) => setModel((m) => ({ ...m, [key]: e.target.value }))}
        className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 font-mono text-sm text-zinc-100 outline-none focus:border-violet-500"
      />
    </label>
  );

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div className="flex items-center gap-3">
        <Cpu className="text-violet-400" size={20} />
        <h2 className="text-lg font-semibold text-zinc-100">Settings</h2>
        <button
          type="button"
          onClick={() => void load()}
          className="ml-auto flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:border-violet-500 hover:text-white"
        >
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/40 bg-red-950/30 px-3 py-2 text-sm text-red-200">
          {error}
        </div>
      )}

      <section className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-zinc-300">Models</h3>
        <form onSubmit={saveModel} className="flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-3">
            {field("model", "Main")}
            {field("fast_model", "Fast")}
            {field("strong_model", "Strong")}
          </div>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-4 py-1.5 text-xs text-white hover:bg-violet-500"
            >
              <Save size={13} /> Save models
            </button>
            {saved && <span className="text-xs text-emerald-400">Saved &amp; hot-swapped.</span>}
          </div>
        </form>
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <User size={15} className="text-zinc-400" />
          <h3 className="text-sm font-semibold text-zinc-300">User profile (memory)</h3>
          <button
            type="button"
            onClick={() => void clearProfile()}
            className="ml-auto flex items-center gap-1.5 rounded-lg border border-zinc-700 px-2.5 py-1 text-[11px] text-zinc-400 hover:border-red-500/50 hover:text-red-300"
          >
            <Trash2 size={12} /> Clear
          </button>
        </div>
        <KeyValues data={profile} />
      </section>

      <section className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-zinc-300">Persona</h3>
        <KeyValues data={persona} />
      </section>
    </div>
  );
}

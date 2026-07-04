"use client";

// Create a model. Adult verification is NOT set here — it is a deliberate,
// separate action on the detail screen (and backend-gated).

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function NewModelPage() {
  const router = useRouter();
  const [stageName, setStageName] = useState("");
  const [realName, setRealName] = useState("");
  const [agencyName, setAgencyName] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const m = await api.createModel({
        stage_name: stageName,
        real_name: realName,
        agency_name: agencyName || undefined,
        birth_date: birthDate || undefined,
      });
      router.push(`/models/${m.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 480 }}>
      <h2>新規モデル登録</h2>
      <div className="card">
        <form onSubmit={submit}>
          <label className="field">
            <span>芸名 *</span>
            <input value={stageName} onChange={(e) => setStageName(e.target.value)} required />
          </label>
          <label className="field">
            <span>本名 *</span>
            <input value={realName} onChange={(e) => setRealName(e.target.value)} required />
          </label>
          <label className="field">
            <span>事務所</span>
            <input value={agencyName} onChange={(e) => setAgencyName(e.target.value)} />
          </label>
          <label className="field">
            <span>生年月日（成人判定の根拠）</span>
            <input type="date" value={birthDate} onChange={(e) => setBirthDate(e.target.value)} />
          </label>
          <button type="submit" disabled={busy || !stageName || !realName}>
            {busy ? "登録中…" : "登録"}
          </button>
        </form>
        {error && <p className="error">{error}</p>}
      </div>
    </div>
  );
}

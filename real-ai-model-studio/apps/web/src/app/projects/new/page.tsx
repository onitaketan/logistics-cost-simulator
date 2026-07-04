"use client";

// Create a project. Requirements, model assignment and compliance checks happen
// on the detail screen after creation.

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function NewProjectPage() {
  const router = useRouter();
  const [projectName, setProjectName] = useState("");
  const [clientName, setClientName] = useState("");
  const [category, setCategory] = useState("");
  const [deadline, setDeadline] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const p = await api.createProject({
        project_name: projectName,
        client_name: clientName || undefined,
        product_category: category || undefined,
        deadline: deadline || undefined,
      });
      router.push(`/projects/${p.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 480 }}>
      <h2>新規案件作成</h2>
      <div className="card">
        <form onSubmit={submit}>
          <label className="field">
            <span>案件名 *</span>
            <input value={projectName} onChange={(e) => setProjectName(e.target.value)} required />
          </label>
          <label className="field">
            <span>クライアント</span>
            <input value={clientName} onChange={(e) => setClientName(e.target.value)} />
          </label>
          <label className="field">
            <span>商品カテゴリ</span>
            <input value={category} onChange={(e) => setCategory(e.target.value)} />
          </label>
          <label className="field">
            <span>納期</span>
            <input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
          </label>
          <button type="submit" disabled={busy || !projectName}>
            {busy ? "作成中…" : "作成"}
          </button>
        </form>
        {error && <p className="error">{error}</p>}
      </div>
    </div>
  );
}

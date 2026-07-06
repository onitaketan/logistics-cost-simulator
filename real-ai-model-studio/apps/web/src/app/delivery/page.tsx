"use client";

// Delivery Management (docs/02 §9/§11). Create a delivery record from pickers
// (project → its approved outputs) — no raw UUIDs. Only approved outputs are
// deliverable; that rule lives in the backend. We simply submit and surface
// whatever error the API returns (e.g. "output is not approved"). Existing
// deliveries for the project are listed below.

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { MEDIA_SCOPE, REGION_SCOPE } from "@rams/shared-types";
import type { Project } from "@rams/shared-types";
import type { Delivery, DeliverySummary, Output } from "@/types";

export default function DeliveryPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [outputs, setOutputs] = useState<Output[]>([]);
  const [deliveries, setDeliveries] = useState<DeliverySummary[]>([]);
  const [outputId, setOutputId] = useState("");
  const [deliveredTo, setDeliveredTo] = useState("");
  const [method, setMethod] = useState("secure_download");
  const [media, setMedia] = useState<string[]>([MEDIA_SCOPE[0]]);
  const [region, setRegion] = useState<string[]>([REGION_SCOPE[0]]);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  const [result, setResult] = useState<Delivery | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listProjects().then(setProjects).catch((e) => setError((e as Error).message));
  }, []);

  function loadDeliveries(pid: string) {
    api.listDeliveries(pid).then(setDeliveries).catch(() => setDeliveries([]));
  }

  // Collect this project's approved outputs by walking its generations. The
  // backend still enforces deliverability — this is only to avoid pasting UUIDs.
  async function loadApprovedOutputs(pid: string) {
    try {
      const gens = await api.listGenerations(pid);
      const lists = await Promise.all(
        gens.map((g) => api.listOutputs(g.id).catch(() => [] as Output[])),
      );
      setOutputs(lists.flat().filter((o) => o.output_status === "approved"));
    } catch {
      setOutputs([]);
    }
  }

  async function pickProject(v: string) {
    setProjectId(v);
    setOutputId("");
    setOutputs([]);
    setDeliveries([]);
    setResult(null);
    setError(null);
    if (!v) return;
    loadDeliveries(v);
    await loadApprovedOutputs(v);
  }

  function toggle(list: string[], set: (v: string[]) => void, v: string) {
    set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    setBusy(true);
    try {
      const d = await api.createDelivery({
        project_id: projectId,
        output_id: outputId,
        delivered_to: deliveredTo,
        delivery_method: method,
        usage_media: media,
        usage_region: region,
        usage_start: start || undefined,
        usage_end: end || undefined,
      });
      setResult(d);
      loadDeliveries(projectId);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const fmt = (v: string[] | string | null) =>
    Array.isArray(v) ? v.join(", ") || "—" : v ?? "—";

  return (
    <div>
      <h2>Delivery</h2>
      <div className="card" style={{ maxWidth: 560 }}>
        <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
          承認済みの出力のみ納品可能です。未承認の場合はバックエンドがエラーを返します。
        </p>
        <form onSubmit={submit}>
          <label className="field">
            <span>案件</span>
            <select value={projectId} onChange={(e) => pickProject(e.target.value)} required>
              <option value="">選択してください</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.project_name}
                  {p.client_name ? `（${p.client_name}）` : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>納品する出力（承認済み）</span>
            <select
              value={outputId}
              onChange={(e) => setOutputId(e.target.value)}
              disabled={!projectId}
              required
            >
              <option value="">選択してください</option>
              {outputs.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.id.slice(0, 8)} — {o.width ?? "?"}×{o.height ?? "?"}
                </option>
              ))}
            </select>
          </label>
          {projectId && outputs.length === 0 && (
            <p className="muted" style={{ fontSize: 12 }}>
              この案件には承認済みの出力がありません。
            </p>
          )}
          <label className="field">
            <span>納品先</span>
            <input value={deliveredTo} onChange={(e) => setDeliveredTo(e.target.value)} required />
          </label>
          <label className="field">
            <span>納品方法</span>
            <select value={method} onChange={(e) => setMethod(e.target.value)}>
              <option value="secure_download">secure_download</option>
              <option value="email">email</option>
              <option value="api">api</option>
            </select>
          </label>
          <div className="field">
            <span>利用媒体</span>
            <div>
              {MEDIA_SCOPE.map((m) => (
                <label key={m} style={{ marginRight: 12 }}>
                  <input type="checkbox" checked={media.includes(m)} onChange={() => toggle(media, setMedia, m)} /> {m}
                </label>
              ))}
            </div>
          </div>
          <div className="field">
            <span>利用地域</span>
            <div>
              {REGION_SCOPE.map((r) => (
                <label key={r} style={{ marginRight: 12 }}>
                  <input type="checkbox" checked={region.includes(r)} onChange={() => toggle(region, setRegion, r)} /> {r}
                </label>
              ))}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <label className="field" style={{ flex: 1 }}>
              <span>利用開始</span>
              <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
            </label>
            <label className="field" style={{ flex: 1 }}>
              <span>利用終了</span>
              <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
            </label>
          </div>
          <button type="submit" disabled={busy || !projectId || !outputId || !deliveredTo}>
            {busy ? "登録中…" : "納品登録"}
          </button>
        </form>
        {error && <p className="error">{error}</p>}
        {result && (
          <p style={{ color: "var(--ok)" }}>納品を登録しました（delivery: {result.id}）。</p>
        )}
      </div>

      {projectId && (
        <div className="card">
          <h3>この案件の納品履歴</h3>
          <table>
            <thead>
              <tr>
                <th>納品先</th><th>方法</th><th>媒体</th><th>地域</th>
                <th>期間</th><th>状態</th>
              </tr>
            </thead>
            <tbody>
              {deliveries.map((d) => (
                <tr key={d.id}>
                  <td>{d.delivered_to}</td>
                  <td>{d.delivery_method}</td>
                  <td>{fmt(d.usage_media)}</td>
                  <td>{fmt(d.usage_region)}</td>
                  <td>{(d.usage_start ?? "—")} 〜 {(d.usage_end ?? "—")}</td>
                  <td>{d.status}</td>
                </tr>
              ))}
              {deliveries.length === 0 && (
                <tr><td colSpan={6} className="muted">納品履歴がありません。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

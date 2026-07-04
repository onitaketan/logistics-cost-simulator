"use client";

// Delivery Management (docs/02 §9/§11). Create a delivery record. Only approved
// outputs are deliverable — that rule lives in the backend; here we simply submit
// and surface whatever error the API returns (e.g. "output is not approved").

import { useState } from "react";
import { api } from "@/lib/api";
import { MEDIA_SCOPE, REGION_SCOPE } from "@rams/shared-types";
import type { Delivery } from "@/types";

export default function DeliveryPage() {
  const [projectId, setProjectId] = useState("");
  const [outputId, setOutputId] = useState("");
  const [deliveredTo, setDeliveredTo] = useState("");
  const [method, setMethod] = useState("secure_download");
  const [media, setMedia] = useState<string>(MEDIA_SCOPE[0]);
  const [region, setRegion] = useState<string>(REGION_SCOPE[0]);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  const [result, setResult] = useState<Delivery | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
        usage_media: [media],
        usage_region: [region],
        usage_start: start || undefined,
        usage_end: end || undefined,
      });
      setResult(d);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 560 }}>
      <h2>Delivery</h2>
      <div className="card">
        <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
          承認済みの出力のみ納品可能です。未承認の場合はバックエンドがエラーを返します。
        </p>
        <form onSubmit={submit}>
          <label className="field">
            <span>project_id</span>
            <input value={projectId} onChange={(e) => setProjectId(e.target.value)} required />
          </label>
          <label className="field">
            <span>output_id</span>
            <input value={outputId} onChange={(e) => setOutputId(e.target.value)} required />
          </label>
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
          <label className="field">
            <span>利用媒体</span>
            <select value={media} onChange={(e) => setMedia(e.target.value)}>
              {MEDIA_SCOPE.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>利用地域</span>
            <select value={region} onChange={(e) => setRegion(e.target.value)}>
              {REGION_SCOPE.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </label>
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
    </div>
  );
}

"use client";

// Audit Log (docs/02 §11). Filter by action_type / target_type and render the log
// table. Every generation/revision/approval/delivery/download is recorded backend-
// side; this screen just reads it.

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AuditLog } from "@/types";

const ACTION_TYPES = ["", "create", "update", "generate", "review", "approve", "deliver", "download"];
const TARGET_TYPES = ["", "model", "project", "generation", "output", "delivery", "contract", "permission"];

export default function AuditPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [actionType, setActionType] = useState("");
  const [targetType, setTargetType] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    api
      .listAuditLogs({
        action_type: actionType || undefined,
        target_type: targetType || undefined,
        limit: 100,
      })
      .then(setLogs)
      .catch((e) => setError((e as Error).message));
  }, [actionType, targetType]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <h2>Audit Log</h2>
      <div className="card">
        <div style={{ display: "flex", gap: 12, alignItems: "flex-end" }}>
          <label className="field" style={{ marginBottom: 0 }}>
            <span>アクション</span>
            <select value={actionType} onChange={(e) => setActionType(e.target.value)}>
              {ACTION_TYPES.map((a) => (
                <option key={a} value={a}>{a || "すべて"}</option>
              ))}
            </select>
          </label>
          <label className="field" style={{ marginBottom: 0 }}>
            <span>対象種別</span>
            <select value={targetType} onChange={(e) => setTargetType(e.target.value)}>
              {TARGET_TYPES.map((t) => (
                <option key={t} value={t}>{t || "すべて"}</option>
              ))}
            </select>
          </label>
          <button onClick={load}>再取得</button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>日時</th>
              <th>ユーザー</th>
              <th>アクション</th>
              <th>対象種別</th>
              <th>対象ID</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((l) => (
              <tr key={l.id}>
                <td>{l.created_at}</td>
                <td>{l.user_id ?? "—"}</td>
                <td>{l.action_type}</td>
                <td>{l.target_type}</td>
                <td>{l.target_id ?? "—"}</td>
              </tr>
            ))}
            {logs.length === 0 && !error && (
              <tr>
                <td colSpan={5} className="muted">ログがありません。</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

"use client";

// Audit Log (docs/02 §11). Filter by action_type / target_type and render the log
// table. Every generation/revision/approval/delivery/download is recorded backend-
// side; this screen just reads it.

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Loading } from "@/components/Loading";
import type { AuditLog } from "@/types";

const ACTION_TYPES = ["", "create", "update", "generate", "review", "approve", "deliver", "download", "view", "login", "delete"];
const TARGET_TYPES = ["", "model", "project", "generation", "output", "delivery", "contract", "permission", "user", "compliance_check"];

export default function AuditPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [actionType, setActionType] = useState("");
  const [targetType, setTargetType] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const filters = useCallback(
    () => ({
      action_type: actionType || undefined,
      target_type: targetType || undefined,
      from: dateFrom || undefined,
      to: dateTo || undefined,
    }),
    [actionType, targetType, dateFrom, dateTo],
  );

  const load = useCallback(() => {
    setError(null);
    setLoading(true);
    api
      .listAuditLogs({ ...filters(), limit: 100 })
      .then(setLogs)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [filters]);

  useEffect(() => {
    load();
  }, [load]);

  async function downloadCsv() {
    setError(null);
    try {
      const blob = await api.exportAuditCsv(filters());
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "audit_logs.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div>
      <h2>Audit Log</h2>
      <div className="card">
        <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
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
          <label className="field" style={{ marginBottom: 0 }}>
            <span>開始日</span>
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label className="field" style={{ marginBottom: 0 }}>
            <span>終了日</span>
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
          <button onClick={load}>再取得</button>
          <button className="ghost" onClick={downloadCsv}>CSVエクスポート</button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}

      {loading ? (
        <Loading label="監査ログを読み込んでいます…" />
      ) : (
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
      )}
    </div>
  );
}

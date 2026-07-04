"use client";

// Model List (docs/02 §5). Small profile images, permission badges, status.
// Enlarged images are gated to privileged roles (not implemented in scaffold).

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Model } from "@rams/shared-types";

export default function ModelsPage() {
  const [models, setModels] = useState<Model[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listModels().then(setModels).catch((e) => setError((e as Error).message));
  }, []);

  return (
    <div>
      <h2>Models</h2>
      {error && <p style={{ color: "var(--ng)" }}>{error}（要ログイン / API起動）</p>}
      <div className="card">
        <table>
          <thead>
            <tr><th>芸名</th><th>事務所</th><th>成人確認</th><th>状態</th></tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr key={m.id}>
                <td>{m.stage_name}</td>
                <td>{m.agency_name ?? "—"}</td>
                <td>{m.adult_verified ? "✓ 確認済" : "未確認"}</td>
                <td>{m.status}</td>
              </tr>
            ))}
            {models.length === 0 && !error && (
              <tr><td colSpan={4} style={{ color: "#889" }}>データがありません。</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

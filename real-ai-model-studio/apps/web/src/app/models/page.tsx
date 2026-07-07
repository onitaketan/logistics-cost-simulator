"use client";

// Model List (docs/02 §5). Small profile images, permission badges, status.
// Enlarged images are gated to privileged roles (backend-enforced).

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Loading } from "@/components/Loading";
import type { Model } from "@rams/shared-types";

export default function ModelsPage() {
  const router = useRouter();
  const [models, setModels] = useState<Model[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listModels()
      .then(setModels)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2>Models</h2>
        <button onClick={() => router.push("/models/new")}>新規モデル登録</button>
      </div>
      {error && <p className="error">{error}</p>}
      {loading ? (
        <Loading label="モデルを読み込んでいます…" />
      ) : (
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>芸名</th>
              <th>事務所</th>
              <th>成人確認</th>
              <th>状態</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr key={m.id}>
                <td>{m.stage_name}</td>
                <td>{m.agency_name ?? "—"}</td>
                <td>
                  {m.adult_verified ? (
                    <span className="badge ok">確認済</span>
                  ) : (
                    <span className="badge ng">未確認</span>
                  )}
                </td>
                <td>{m.status}</td>
                <td>
                  <Link href={`/models/${m.id}`}>詳細</Link>
                </td>
              </tr>
            ))}
            {models.length === 0 && !error && (
              <tr>
                <td colSpan={5} className="muted">データがありません。</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      )}
    </div>
  );
}

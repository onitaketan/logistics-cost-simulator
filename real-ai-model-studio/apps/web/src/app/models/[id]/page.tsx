"use client";

// Model detail (docs/02 §6). Tabs: Overview / Contract / Permissions / Assets.
// The adult-verification action is here; it is backend-gated (a model cannot be
// used for generation unless the backend confirms adult_verified).

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Model } from "@rams/shared-types";
import type { Asset, Contract, Permission } from "@/types";

type Tab = "overview" | "contract" | "permissions" | "assets";

export default function ModelDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [tab, setTab] = useState<Tab>("overview");
  const [model, setModel] = useState<Model | null>(null);
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadModel = useCallback(() => {
    api.getModel(id).then(setModel).catch((e) => setError((e as Error).message));
  }, [id]);

  useEffect(() => {
    loadModel();
    api.listContracts(id).then(setContracts).catch(() => setContracts([]));
    api.listPermissions(id).then(setPermissions).catch(() => setPermissions([]));
    api.listAssets(id).then(setAssets).catch(() => setAssets([]));
  }, [id, loadModel]);

  async function toggleAdult(next: boolean) {
    setError(null);
    setBusy(true);
    try {
      const updated = await api.setAdultVerification(id, next);
      setModel(updated);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!model) {
    return (
      <div>
        <Link href="/models">← Models</Link>
        {error ? <p className="error">{error}</p> : <p className="muted">読み込み中…</p>}
      </div>
    );
  }

  return (
    <div>
      <Link href="/models">← Models</Link>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2>{model.stage_name}</h2>
        <div>
          {model.adult_verified ? (
            <button className="ghost" disabled={busy} onClick={() => toggleAdult(false)}>
              成人確認を取り消す
            </button>
          ) : (
            <button disabled={busy} onClick={() => toggleAdult(true)}>
              成人確認を行う
            </button>
          )}
        </div>
      </div>
      {error && <p className="error">{error}</p>}

      <div className="tabs">
        {(["overview", "contract", "permissions", "assets"] as Tab[]).map((t) => (
          <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
            {t === "overview" && "概要"}
            {t === "contract" && "契約"}
            {t === "permissions" && "許諾"}
            {t === "assets" && "素材"}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="card">
          <p>芸名: {model.stage_name}</p>
          <p>事務所: {model.agency_name ?? "—"}</p>
          <p>生年月日: {model.birth_date ?? "—"}</p>
          <p>
            成人確認:{" "}
            {model.adult_verified ? (
              <span className="badge ok">確認済</span>
            ) : (
              <span className="badge ng">未確認</span>
            )}
          </p>
          <p>状態: {model.status}</p>
        </div>
      )}

      {tab === "contract" && (
        <div className="card">
          <h3>契約</h3>
          <table>
            <thead>
              <tr>
                <th>種別</th>
                <th>開始</th>
                <th>終了</th>
                <th>AI生成</th>
                <th>AI学習</th>
                <th>海外</th>
              </tr>
            </thead>
            <tbody>
              {contracts.map((c) => (
                <tr key={c.id}>
                  <td>{c.contract_type ?? "—"}</td>
                  <td>{c.contract_start ?? "—"}</td>
                  <td>{c.contract_end ?? "—"}</td>
                  <td>{c.ai_generation_allowed ? "可" : "不可"}</td>
                  <td>{c.ai_training_allowed ? "可" : "不可"}</td>
                  <td>{c.overseas_allowed ? "可" : "不可"}</td>
                </tr>
              ))}
              {contracts.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted">契約データがありません。</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {tab === "permissions" && (
        <div className="card">
          <h3>許諾範囲</h3>
          <table>
            <thead>
              <tr>
                <th>項目</th>
                <th>可否</th>
                <th>承認レベル</th>
                <th>備考</th>
              </tr>
            </thead>
            <tbody>
              {permissions.map((p) => (
                <tr key={p.id}>
                  <td>{p.scope_type}</td>
                  <td>{p.allowed}</td>
                  <td>{p.approval_level ?? "—"}</td>
                  <td>{p.notes ?? "—"}</td>
                </tr>
              ))}
              {permissions.length === 0 && (
                <tr>
                  <td colSpan={4} className="muted">許諾データがありません。</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {tab === "assets" && (
        <div className="card">
          <h3>素材</h3>
          <table>
            <thead>
              <tr>
                <th>種別</th>
                <th>用途</th>
                <th>同意</th>
                <th>登録日</th>
              </tr>
            </thead>
            <tbody>
              {assets.map((a) => (
                <tr key={a.id}>
                  <td>{a.asset_type}</td>
                  <td>{a.usage_type}</td>
                  <td>{a.consent_confirmed ? "確認済" : "未確認"}</td>
                  <td>{a.created_at ?? "—"}</td>
                </tr>
              ))}
              {assets.length === 0 && (
                <tr>
                  <td colSpan={4} className="muted">素材がありません。</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

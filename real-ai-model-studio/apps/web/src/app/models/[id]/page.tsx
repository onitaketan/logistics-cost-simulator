"use client";

// Model detail (docs/02 §6). Tabs: Overview / Contract / Permissions / Assets.
// Each tab lists existing records AND lets an authorized user create new ones, so
// a model can be fully set up through the UI (register → contract → permission →
// assets). Adult verification is here and is backend-gated. The UI carries no
// compliance logic — the backend decides what is allowed.

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { MEDIA_SCOPE, REGION_SCOPE } from "@rams/shared-types";
import type { Model } from "@rams/shared-types";
import type { Asset, Contract, Permission } from "@/types";

type Tab = "overview" | "contract" | "permissions" | "assets";

const yn = (b: boolean | undefined) => (b ? "可" : "不可");

// Permission matrix (docs/02 §6). A read-only, aggregated view derived from the
// contracts + permissions lists — NO compliance logic, just a legible summary of
// what the backend records say. Boolean rows are "可" if ANY record allows it.
type Verdict = "yes" | "no" | "conditional";

interface MatrixRow {
  label: string;
  verdict: Verdict;
  detail?: string;
  approval: string;
}

const verdictBadge: Record<Verdict, { cls: string; text: string }> = {
  yes: { cls: "ok", text: "可" },
  conditional: { cls: "conditional", text: "条件付" },
  no: { cls: "ng", text: "不可" },
};

function buildMatrix(contracts: Contract[], permissions: Permission[]): MatrixRow[] {
  const anyContract = (f: (c: Contract) => boolean | undefined) =>
    contracts.some((c) => !!f(c));
  const anyPerm = (f: (p: Permission) => boolean | undefined) =>
    permissions.some((p) => !!f(p));
  // Distinct approval levels required across permissions (fallback to legal norm).
  const approvals = Array.from(
    new Set(permissions.map((p) => String(p.approval_required_level)).filter(Boolean)),
  );
  const approvalOf = (fallback: string) =>
    approvals.length > 0 ? approvals.join(" / ") : fallback;

  // Bath is a tri-state per permission; roll up to the most permissive value.
  const bathValues = permissions.map((p) => p.bath_allowed);
  const bath: Verdict = bathValues.includes("yes")
    ? "yes"
    : bathValues.includes("conditional")
      ? "conditional"
      : "no";

  const maxExposure = permissions.reduce(
    (m, p) => Math.max(m, p.exposure_level_max ?? 0),
    0,
  );

  const b = (v: boolean): Verdict => (v ? "yes" : "no");

  return [
    {
      label: "AI生成",
      verdict: b(anyContract((c) => c.ai_generation_allowed)),
      approval: approvalOf("internal / legal"),
    },
    {
      label: "AI学習",
      verdict: b(anyContract((c) => c.ai_training_allowed)),
      approval: approvalOf("legal"),
    },
    {
      label: "水着",
      verdict: b(anyPerm((p) => p.swimwear_allowed)),
      approval: approvalOf("legal"),
    },
    {
      label: "下着",
      verdict: b(anyPerm((p) => p.underwear_allowed)),
      approval: approvalOf("person / agency"),
    },
    {
      label: "入浴",
      verdict: bath,
      approval: approvalOf("person / agency"),
    },
    {
      label: "海外",
      verdict: b(anyPerm((p) => p.overseas_allowed)),
      approval: approvalOf("agency"),
    },
    {
      label: "露出上限",
      verdict: maxExposure > 0 ? "conditional" : "no",
      detail: `レベル ${maxExposure} / 5`,
      approval: approvalOf("legal"),
    },
  ];
}

export default function ModelDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [tab, setTab] = useState<Tab>("overview");
  const [model, setModel] = useState<Model | null>(null);
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadModel = useCallback(() => {
    api.getModel(id).then(setModel).catch((e) => setError((e as Error).message));
  }, [id]);
  const loadContracts = useCallback(() => {
    api.listContracts(id).then(setContracts).catch(() => setContracts([]));
  }, [id]);
  const loadPermissions = useCallback(() => {
    api.listPermissions(id).then(setPermissions).catch(() => setPermissions([]));
  }, [id]);
  const loadAssets = useCallback(() => {
    api.listAssets(id).then(setAssets).catch(() => setAssets([]));
  }, [id]);

  useEffect(() => {
    loadModel();
    loadContracts();
    loadPermissions();
    loadAssets();
  }, [loadModel, loadContracts, loadPermissions, loadAssets]);

  function flash(msg: string) {
    setNotice(msg);
    setError(null);
  }

  async function toggleAdult(next: boolean) {
    setError(null);
    setBusy(true);
    try {
      setModel(await api.setAdultVerification(id, next));
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
      {notice && <p style={{ color: "var(--ok)" }}>{notice}</p>}

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
        <>
          <div className="card">
            <h3>契約</h3>
            <table>
              <thead>
                <tr>
                  <th>契約番号</th><th>種別</th><th>開始</th><th>終了</th>
                  <th>AI生成</th><th>AI学習</th>
                </tr>
              </thead>
              <tbody>
                {contracts.map((c) => (
                  <tr key={c.id}>
                    <td>{c.contract_number ?? "—"}</td>
                    <td>{c.contract_type ?? "—"}</td>
                    <td>{c.contract_start ?? "—"}</td>
                    <td>{c.contract_end ?? "—"}</td>
                    <td>{yn(c.ai_generation_allowed)}</td>
                    <td>{yn(c.ai_training_allowed)}</td>
                  </tr>
                ))}
                {contracts.length === 0 && (
                  <tr><td colSpan={6} className="muted">契約データがありません。</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <ContractForm modelId={id} onDone={() => { loadContracts(); flash("契約を登録しました。"); }} onError={setError} />
        </>
      )}

      {tab === "permissions" && (
        <>
          <div className="card">
            <h3>許諾マトリクス</h3>
            {permissions.length === 0 && contracts.length === 0 ? (
              <p className="muted">契約・許諾データがありません。</p>
            ) : (
              <table>
                <thead>
                  <tr><th>項目</th><th>可否</th><th>承認レベル</th></tr>
                </thead>
                <tbody>
                  {buildMatrix(contracts, permissions).map((row) => {
                    const bd = verdictBadge[row.verdict];
                    return (
                      <tr key={row.label}>
                        <td>{row.label}</td>
                        <td>
                          <span className={`badge ${bd.cls}`}>{bd.text}</span>
                          {row.detail && (
                            <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>
                              {row.detail}
                            </span>
                          )}
                        </td>
                        <td>{row.approval}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
          <div className="card">
            <h3>許諾範囲</h3>
            <table>
              <thead>
                <tr>
                  <th>媒体</th><th>地域</th><th>水着</th><th>下着</th><th>入浴</th>
                  <th>露出上限</th><th>承認</th>
                </tr>
              </thead>
              <tbody>
                {permissions.map((p) => (
                  <tr key={p.id}>
                    <td>{(p.media_scope ?? []).join(", ") || "—"}</td>
                    <td>{(p.region_scope ?? []).join(", ") || "—"}</td>
                    <td>{yn(p.swimwear_allowed)}</td>
                    <td>{yn(p.underwear_allowed)}</td>
                    <td>{p.bath_allowed}</td>
                    <td>{p.exposure_level_max}</td>
                    <td>{p.approval_required_level}</td>
                  </tr>
                ))}
                {permissions.length === 0 && (
                  <tr><td colSpan={7} className="muted">許諾データがありません。</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <PermissionForm
            modelId={id}
            contracts={contracts}
            onDone={() => { loadPermissions(); flash("許諾範囲を登録しました。"); }}
            onError={setError}
          />
        </>
      )}

      {tab === "assets" && (
        <>
          <div className="card">
            <h3>素材</h3>
            <table>
              <thead>
                <tr><th>種別</th><th>用途</th><th>ファイル名</th><th>同意</th></tr>
              </thead>
              <tbody>
                {assets.map((a) => (
                  <tr key={a.id}>
                    <td>{a.asset_type}</td>
                    <td>{a.usage_type}</td>
                    <td>{a.original_filename ?? "—"}</td>
                    <td>{a.consent_confirmed ? "確認済" : "未確認"}</td>
                  </tr>
                ))}
                {assets.length === 0 && (
                  <tr><td colSpan={4} className="muted">素材がありません。</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <AssetForm modelId={id} onDone={() => { loadAssets(); flash("素材をアップロードしました。"); }} onError={setError} />
        </>
      )}
    </div>
  );
}

// ---------------- Contract form ----------------
function ContractForm({ modelId, onDone, onError }: {
  modelId: string; onDone: () => void; onError: (m: string) => void;
}) {
  const [number, setNumber] = useState("");
  const [type, setType] = useState("base");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [gen, setGen] = useState(true);
  const [train, setTrain] = useState(false);
  const [postUse, setPostUse] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.createContract(modelId, {
        contract_number: number,
        contract_type: type,
        contract_start: start,
        contract_end: end,
        ai_generation_allowed: gen,
        ai_training_allowed: train,
        post_contract_use_allowed: postUse,
      });
      onDone();
      setNumber("");
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h3>契約を追加</h3>
      <form onSubmit={submit}>
        <label className="field"><span>契約番号 *</span>
          <input value={number} onChange={(e) => setNumber(e.target.value)} required /></label>
        <label className="field"><span>種別</span>
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="base">base</option>
            <option value="individual">individual</option>
            <option value="additional_consent">additional_consent</option>
          </select></label>
        <div style={{ display: "flex", gap: 8 }}>
          <label className="field" style={{ flex: 1 }}><span>開始日 *</span>
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} required /></label>
          <label className="field" style={{ flex: 1 }}><span>終了日 *</span>
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} required /></label>
        </div>
        <label style={{ display: "block", marginBottom: 6 }}>
          <input type="checkbox" checked={gen} onChange={(e) => setGen(e.target.checked)} /> AI生成を許可
        </label>
        <label style={{ display: "block", marginBottom: 6 }}>
          <input type="checkbox" checked={train} onChange={(e) => setTrain(e.target.checked)} /> AI学習を許可
        </label>
        <label style={{ display: "block", marginBottom: 10 }}>
          <input type="checkbox" checked={postUse} onChange={(e) => setPostUse(e.target.checked)} /> 契約終了後の利用を許可
        </label>
        <button type="submit" disabled={busy || !number || !start || !end}>
          {busy ? "登録中…" : "契約を登録"}
        </button>
      </form>
    </div>
  );
}

// ---------------- Permission form ----------------
function PermissionForm({ modelId, contracts, onDone, onError }: {
  modelId: string; contracts: Contract[]; onDone: () => void; onError: (m: string) => void;
}) {
  const [contractId, setContractId] = useState("");
  const [media, setMedia] = useState<string[]>([]);
  const [region, setRegion] = useState<string[]>([]);
  const [products, setProducts] = useState("");
  const [swim, setSwim] = useState(false);
  const [under, setUnder] = useState(false);
  const [bath, setBath] = useState("no");
  const [expMax, setExpMax] = useState(0);
  const [overseas, setOverseas] = useState(false);
  const [approval, setApproval] = useState("legal");
  const [busy, setBusy] = useState(false);

  function toggle(list: string[], set: (v: string[]) => void, v: string) {
    set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.createPermission(modelId, {
        contract_id: contractId,
        media_scope: media,
        region_scope: region,
        product_scope: products.split(",").map((s) => s.trim()).filter(Boolean),
        swimwear_allowed: swim,
        underwear_allowed: under,
        bath_allowed: bath,
        exposure_level_max: expMax,
        overseas_allowed: overseas,
        approval_required_level: approval,
      });
      onDone();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h3>許諾範囲を追加</h3>
      {contracts.length === 0 ? (
        <p className="muted">先に契約を登録してください（許諾は契約に紐づきます）。</p>
      ) : (
        <form onSubmit={submit}>
          <label className="field"><span>紐づく契約 *</span>
            <select value={contractId} onChange={(e) => setContractId(e.target.value)} required>
              <option value="">選択してください</option>
              {contracts.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.contract_number ?? c.id}（〜{c.contract_end ?? "?"}）
                </option>
              ))}
            </select></label>
          <div className="field"><span>媒体</span>
            <div>{MEDIA_SCOPE.map((m) => (
              <label key={m} style={{ marginRight: 12 }}>
                <input type="checkbox" checked={media.includes(m)} onChange={() => toggle(media, setMedia, m)} /> {m}
              </label>
            ))}</div>
          </div>
          <div className="field"><span>地域</span>
            <div>{REGION_SCOPE.map((r) => (
              <label key={r} style={{ marginRight: 12 }}>
                <input type="checkbox" checked={region.includes(r)} onChange={() => toggle(region, setRegion, r)} /> {r}
              </label>
            ))}</div>
          </div>
          <label className="field"><span>許可商品カテゴリ（カンマ区切り）</span>
            <input value={products} onChange={(e) => setProducts(e.target.value)} placeholder="beverage, apparel" /></label>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <label><input type="checkbox" checked={swim} onChange={(e) => setSwim(e.target.checked)} /> 水着許可</label>
            <label><input type="checkbox" checked={under} onChange={(e) => setUnder(e.target.checked)} /> 下着許可</label>
            <label><input type="checkbox" checked={overseas} onChange={(e) => setOverseas(e.target.checked)} /> 海外配信許可</label>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <label className="field" style={{ flex: 1 }}><span>入浴</span>
              <select value={bath} onChange={(e) => setBath(e.target.value)}>
                <option value="no">no</option><option value="conditional">conditional</option><option value="yes">yes</option>
              </select></label>
            <label className="field" style={{ flex: 1 }}><span>露出上限(0-4)</span>
              <select value={expMax} onChange={(e) => setExpMax(Number(e.target.value))}>
                {[0, 1, 2, 3, 4].map((v) => <option key={v} value={v}>{v}</option>)}
              </select></label>
            <label className="field" style={{ flex: 1 }}><span>基本承認</span>
              <select value={approval} onChange={(e) => setApproval(e.target.value)}>
                <option value="internal">internal</option><option value="legal">legal</option>
                <option value="agency">agency</option><option value="person">person</option>
              </select></label>
          </div>
          <button type="submit" disabled={busy || !contractId}>
            {busy ? "登録中…" : "許諾を登録"}
          </button>
        </form>
      )}
    </div>
  );
}

// ---------------- Asset upload ----------------
function AssetForm({ modelId, onDone, onError }: {
  modelId: string; onDone: () => void; onError: (m: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [assetType, setAssetType] = useState("reference");
  const [usageType, setUsageType] = useState("reference");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    try {
      await api.uploadAsset(modelId, file, assetType, usageType, consent);
      onDone();
      setFile(null);
      setConsent(false);
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h3>素材をアップロード</h3>
      <form onSubmit={submit}>
        <label className="field"><span>ファイル *</span>
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required /></label>
        <div style={{ display: "flex", gap: 8 }}>
          <label className="field" style={{ flex: 1 }}><span>種別</span>
            <select value={assetType} onChange={(e) => setAssetType(e.target.value)}>
              {["face", "body", "expression", "pose", "reference", "ng"].map((v) => <option key={v} value={v}>{v}</option>)}
            </select></label>
          <label className="field" style={{ flex: 1 }}><span>用途</span>
            <select value={usageType} onChange={(e) => setUsageType(e.target.value)}>
              {["reference", "training", "review_only", "prohibited"].map((v) => <option key={v} value={v}>{v}</option>)}
            </select></label>
        </div>
        <label style={{ display: "block", marginBottom: 10 }}>
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /> 本人・事務所の同意を確認済み（学習利用には必須）
        </label>
        <button type="submit" disabled={busy || !file}>
          {busy ? "アップロード中…" : "アップロード"}
        </button>
      </form>
    </div>
  );
}

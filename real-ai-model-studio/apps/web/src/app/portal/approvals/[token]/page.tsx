"use client";

// External approval PORTAL (docs/05 §9). An agency or the person themselves opens
// a single-use, expiring link and records a sign-off decision WITHOUT logging in.
// The token in the URL is the only credential — this page renders bare (no app
// shell, see Shell.tsx) and every call goes through the unauthenticated
// api.getPortalApproval / api.submitPortalApproval (no Bearer, no 401 redirect).

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, resolveFileUrl } from "@/lib/api";
import type { PortalApprovalView } from "@/types";

const LEVEL_LABELS: Record<string, string> = {
  agency: "事務所",
  person: "本人",
};

const DECISIONS: { value: "approved" | "conditional" | "rejected"; label: string }[] = [
  { value: "approved", label: "承認" },
  { value: "conditional", label: "条件付き" },
  { value: "rejected", label: "却下" },
];

export default function PortalApprovalPage() {
  const params = useParams<{ token: string }>();
  const token = params.token;

  const [view, setView] = useState<PortalApprovalView | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [decision, setDecision] = useState<"approved" | "conditional" | "rejected">("approved");
  const [comment, setComment] = useState("");
  const [approverName, setApproverName] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const v = await api.getPortalApproval(token);
      setView(v);
      setPreviewUrl(v.preview_url ? resolveFileUrl(v.preview_url) : null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      await api.submitPortalApproval(token, {
        decision,
        comment: comment || undefined,
        approver_name: approverName || undefined,
      });
      setDone(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const levelLabel = view ? LEVEL_LABELS[view.level] ?? view.level : "";
  // Closed = the request is no longer awaiting a decision (already recorded or
  // expired). We also treat a just-submitted decision (done) as closed.
  const closed = !!view && (view.already_decided || view.status !== "pending");

  return (
    <div style={{ minHeight: "100vh", background: "#f4f5f7", padding: "32px 16px" }}>
      <div style={{ maxWidth: 560, margin: "0 auto" }}>
        <div style={{ marginBottom: 20 }}>
          <h1 style={{ fontSize: 20, margin: "0 0 4px" }}>外部承認ポータル</h1>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            AI生成画像の承認確認（{levelLabel || "外部"}承認）
          </p>
        </div>

        {loading && <p className="muted">読み込み中…</p>}

        {!loading && error && !view && (
          <div className="card">
            <p className="error" style={{ margin: 0 }}>{error}</p>
            <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
              リンクが無効か、有効期限が切れている可能性があります。
            </p>
          </div>
        )}

        {view && (
          <div className="card">
            <div style={{ display: "flex", gap: 16 }}>
              <div style={{ textAlign: "center" }}>
                {previewUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={previewUrl} alt="生成画像プレビュー" className="thumb" />
                ) : (
                  <div className="thumb" />
                )}
              </div>
              <div style={{ flex: 1 }}>
                <p style={{ marginTop: 0, marginBottom: 6 }}>
                  <strong>{view.project_name}</strong>
                </p>
                <p className="muted" style={{ fontSize: 13, margin: "2px 0" }}>
                  承認区分: <span className="badge neutral">{levelLabel}</span>
                </p>
                <p className="muted" style={{ fontSize: 13, margin: "2px 0" }}>
                  現在の状態: <span className="badge neutral">{view.status}</span>
                </p>
                <p className="muted" style={{ fontSize: 13, margin: "2px 0" }}>
                  有効期限: {view.expires_at?.slice(0, 19).replace("T", " ")}
                </p>
              </div>
            </div>

            <hr style={{ border: "none", borderTop: "1px solid var(--line)", margin: "16px 0" }} />

            {done ? (
              <div className="notice success" style={{ margin: 0 }}>
                承認結果を記録しました。ご対応ありがとうございました。このリンクは無効になりました。
              </div>
            ) : closed ? (
              <div className="notice" style={{ margin: 0 }}>
                この承認はすでに手続きが完了しているか、有効期限が切れています。
                これ以上の操作はできません。ご確認ありがとうございました。
              </div>
            ) : (
              <div>
                <p style={{ fontSize: 14, marginTop: 0 }}>
                  この画像の使用可否をご判断のうえ、下記より結果をお知らせください。
                </p>

                <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
                  {DECISIONS.map((d) => (
                    <button
                      key={d.value}
                      type="button"
                      className={`small${decision === d.value ? "" : " ghost"}`}
                      onClick={() => setDecision(d.value)}
                    >
                      {d.label}
                    </button>
                  ))}
                </div>

                <label className="field">
                  <span>氏名（任意）</span>
                  <input
                    value={approverName}
                    onChange={(e) => setApproverName(e.target.value)}
                    placeholder="承認者のお名前"
                  />
                </label>

                <label className="field">
                  <span>コメント（任意）</span>
                  <textarea
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    rows={3}
                    placeholder="条件付き承認の条件やご意見があればご記入ください"
                  />
                </label>

                {error && <p className="error">{error}</p>}

                <button
                  type="button"
                  onClick={submit}
                  disabled={busy}
                  style={{ marginTop: 4 }}
                >
                  {busy ? "送信中…" : `この内容で送信（${DECISIONS.find((d) => d.value === decision)?.label}）`}
                </button>
                <p className="muted" style={{ fontSize: 11, marginBottom: 0, marginTop: 8 }}>
                  このリンクは一度きり有効で、送信後は無効になります。
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

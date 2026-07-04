"use client";

// Review & Approval (docs/02 §10). Enter a generation id, list its outputs, and
// per output: set status, add a review, and add an approval. The approvals call
// returns required_approvals + missing_approvals — we surface those so the user
// sees "まだ全承認が揃っていない" until the backend says it is fully approved.

import { useState } from "react";
import { api } from "@/lib/api";
import type { ApprovalLevel, OutputStatus } from "@rams/shared-types";
import type { ApprovalResult, Output } from "@/types";

const OUTPUT_STATUSES: OutputStatus[] = [
  "candidate",
  "selected",
  "rejected",
  "approved",
  "delivered",
];
const APPROVAL_LEVELS: ApprovalLevel[] = ["internal", "legal", "agency", "person", "admin"];
const DECISIONS = ["approved", "conditional", "rejected"];

export default function ReviewPage() {
  const [genId, setGenId] = useState("");
  const [outputs, setOutputs] = useState<Output[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      setOutputs(await api.listOutputs(genId));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div>
      <h2>Review & Approval</h2>
      <div className="card">
        <div style={{ display: "flex", gap: 8 }}>
          <input placeholder="generation_id" value={genId}
            onChange={(e) => setGenId(e.target.value)} style={{ padding: 8, flex: 1 }} />
          <button onClick={load} disabled={!genId}>出力を読み込む</button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}

      {outputs.map((o) => (
        <OutputReviewCard key={o.id} output={o} onError={setError} />
      ))}
      {outputs.length === 0 && !error && (
        <p className="muted">generation_id を入力して出力を読み込んでください。</p>
      )}
    </div>
  );
}

function OutputReviewCard({
  output,
  onError,
}: {
  output: Output;
  onError: (m: string) => void;
}) {
  const [status, setStatus] = useState<OutputStatus>(output.output_status);
  const [currentStatus, setCurrentStatus] = useState<OutputStatus>(output.output_status);

  const [reviewType, setReviewType] = useState("internal");
  const [reviewDecision, setReviewDecision] = useState("approved");
  const [reviewComment, setReviewComment] = useState("");

  const [approvalLevel, setApprovalLevel] = useState<ApprovalLevel>("internal");
  const [approvalDecision, setApprovalDecision] = useState("approved");
  const [approvalComment, setApprovalComment] = useState("");
  const [approvalResult, setApprovalResult] = useState<ApprovalResult | null>(null);

  const [notice, setNotice] = useState<string | null>(null);

  async function applyStatus() {
    onError("");
    try {
      const updated = await api.setOutputStatus(output.id, status);
      setCurrentStatus(updated.output_status);
      setNotice("ステータスを更新しました。");
    } catch (e) {
      onError((e as Error).message);
    }
  }

  async function submitReview() {
    onError("");
    try {
      await api.addReview(output.id, reviewType, reviewDecision, reviewComment || undefined);
      setNotice("レビューを登録しました。");
      setReviewComment("");
    } catch (e) {
      onError((e as Error).message);
    }
  }

  async function submitApproval() {
    onError("");
    try {
      const res = await api.addApproval(
        output.id,
        approvalLevel,
        approvalDecision,
        approvalComment || undefined,
      );
      setApprovalResult(res);
      setCurrentStatus(res.output_status);
      setApprovalComment("");
    } catch (e) {
      onError((e as Error).message);
    }
  }

  return (
    <div className="card">
      <div style={{ display: "flex", gap: 16 }}>
        <div style={{ textAlign: "center" }}>
          <div className="thumb" />
          <div className="muted" style={{ fontSize: 11 }}>
            {output.width ?? "?"}×{output.height ?? "?"}
          </div>
        </div>
        <div style={{ flex: 1 }}>
          <p style={{ marginTop: 0 }}>
            output: {output.id} — 現状態:{" "}
            <span className="badge neutral">{currentStatus}</span>
          </p>

          {/* Set status */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}>
            <select value={status} onChange={(e) => setStatus(e.target.value as OutputStatus)}>
              {OUTPUT_STATUSES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <button className="small" onClick={applyStatus}>状態を更新</button>
          </div>

          {/* Add review */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 10 }}>
            <select value={reviewType} onChange={(e) => setReviewType(e.target.value)}>
              <option value="internal">internal</option>
              <option value="legal">legal</option>
            </select>
            <select value={reviewDecision} onChange={(e) => setReviewDecision(e.target.value)}>
              {DECISIONS.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
            <input placeholder="コメント" value={reviewComment}
              onChange={(e) => setReviewComment(e.target.value)} style={{ padding: 6, flex: 1, minWidth: 160 }} />
            <button className="small" onClick={submitReview}>レビュー追加</button>
          </div>

          {/* Add approval */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <select value={approvalLevel} onChange={(e) => setApprovalLevel(e.target.value as ApprovalLevel)}>
              {APPROVAL_LEVELS.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
            <select value={approvalDecision} onChange={(e) => setApprovalDecision(e.target.value)}>
              {DECISIONS.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
            <input placeholder="コメント" value={approvalComment}
              onChange={(e) => setApprovalComment(e.target.value)} style={{ padding: 6, flex: 1, minWidth: 160 }} />
            <button className="small" onClick={submitApproval}>承認追加</button>
          </div>

          {approvalResult && (
            <div style={{ marginTop: 10, fontSize: 13 }}>
              <p style={{ margin: "4px 0" }}>
                出力状態: <span className="badge neutral">{approvalResult.output_status}</span>
              </p>
              <p style={{ margin: "4px 0" }}>
                必要承認: {approvalResult.required_approvals.join(" ・ ") || "—"}
              </p>
              {approvalResult.missing_approvals.length > 0 ? (
                <p className="error" style={{ margin: "4px 0" }}>
                  未承認: {approvalResult.missing_approvals.join(" ・ ")}（全承認が揃っていません）
                </p>
              ) : (
                <p style={{ color: "var(--ok)", margin: "4px 0" }}>全承認が揃いました。</p>
              )}
            </div>
          )}

          {notice && <p style={{ color: "var(--ok)", fontSize: 12 }}>{notice}</p>}
        </div>
      </div>
    </div>
  );
}

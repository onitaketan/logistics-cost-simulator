"use client";

// Generation Studio (docs/02 §9). Generate is DISABLED unless a compliance check
// exists with status ok/conditional — a UI courtesy only; the backend re-validates
// and the DB trigger enforces regardless. After generation we poll the (synchronous
// mechanism kept as-is) job until completed, then render the outputs.

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, resolveFileUrl } from "@/lib/api";
import type { ComplianceResult, Model, Project } from "@rams/shared-types";
import type { Output, PromptTemplate } from "@/types";

export default function GenerationStudio() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [projectId, setProjectId] = useState("");
  const [modelId, setModelId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [negative, setNegative] = useState("");
  const [check, setCheck] = useState<ComplianceResult | null>(null);
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [templateId, setTemplateId] = useState("");

  // Populate project/model pickers so testers never paste raw UUIDs, and load the
  // active prompt templates for the picker (P1-004).
  useEffect(() => {
    api.listProjects().then(setProjects).catch(() => setProjects([]));
    api.listModels().then(setModels).catch(() => setModels([]));
    api.listPromptTemplates(true).then(setTemplates).catch(() => setTemplates([]));
  }, []);

  // Choosing a template fills the prompt (and negative prompt) fields and records
  // which template was used so the backend can attribute the generation to it.
  function pickTemplate(id: string) {
    setTemplateId(id);
    if (!id) return;
    const t = templates.find((x) => x.id === id);
    if (!t) return;
    setPrompt(t.body);
    setNegative(t.negative_body ?? "");
  }

  const [genId, setGenId] = useState<string | null>(null);
  const [genStatus, setGenStatus] = useState<string | null>(null);
  const [outputs, setOutputs] = useState<Output[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const canGenerate =
    !!check?.compliance_check_id &&
    (check.check_status === "ok" || check.check_status === "conditional");

  // Poll the generation job while it is not terminal.
  useEffect(() => {
    if (!genId) return;
    const terminal = (s: string) => s === "completed" || s === "failed";

    async function poll() {
      try {
        const g = await api.getGeneration(genId as string);
        setGenStatus(g.status);
        if (terminal(g.status)) {
          if (timer.current) clearInterval(timer.current);
          if (g.status === "completed") {
            setOutputs(await api.listOutputs(genId as string));
          }
        }
      } catch (e) {
        if (timer.current) clearInterval(timer.current);
        setError((e as Error).message);
      }
    }

    poll();
    timer.current = setInterval(poll, 2000);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [genId]);

  async function runCheck() {
    setError(null);
    try {
      setCheck(await api.runComplianceCheck(projectId, modelId, prompt || undefined));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function generate() {
    setError(null);
    setOutputs([]);
    setGenStatus(null);
    setBusy(true);
    try {
      const res = await api.createGeneration({
        project_id: projectId,
        model_id: modelId,
        compliance_check_id: check!.compliance_check_id as string,
        prompt_text: prompt,
        negative_prompt_text: negative || undefined,
        generation_params: { output_count: 4, width: 1024, height: 1280 },
        prompt_template_id: templateId || undefined,
      });
      setGenId(res.generation_id);
      setGenStatus(res.status);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const running = genStatus !== null && genStatus !== "completed" && genStatus !== "failed";

  return (
    <div className="cols-2">
      <div>
        <h2>Generation Studio</h2>
        <div className="card">
          <div style={{ display: "flex", gap: 8 }}>
            <select value={projectId} style={{ padding: 8, flex: 1 }}
              onChange={(e) => { setProjectId(e.target.value); setCheck(null); }}>
              <option value="">案件を選択</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.project_name}</option>
              ))}
            </select>
            <select value={modelId} style={{ padding: 8, flex: 1 }}
              onChange={(e) => { setModelId(e.target.value); setCheck(null); }}>
              <option value="">モデルを選択</option>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.stage_name}{m.adult_verified ? "" : "（未成人確認）"}
                </option>
              ))}
            </select>
          </div>
          <select value={templateId} style={{ padding: 8, width: "100%", marginTop: 8 }}
            onChange={(e) => pickTemplate(e.target.value)}>
            <option value="">テンプレート（任意）</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
          <textarea placeholder="プロンプト（許諾範囲内の広告表現）" value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            style={{ width: "100%", padding: 8, minHeight: 90, marginTop: 8 }} />
          <textarea placeholder="ネガティブプロンプト（任意）" value={negative}
            onChange={(e) => setNegative(e.target.value)}
            style={{ width: "100%", padding: 8, minHeight: 50, marginTop: 8 }} />
          <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
            <button onClick={runCheck}>コンプライアンス判定</button>
            <button onClick={generate} disabled={!canGenerate || busy || running}>
              {running ? "生成中…" : "生成する"}
            </button>
          </div>
          {!canGenerate && (
            <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
              判定が OK / 条件付き の場合のみ生成できます。
            </p>
          )}
        </div>

        {genId && (
          <div className="card">
            <h3>生成ジョブ</h3>
            <p>
              generation: {genId} — 状態:{" "}
              <span className="badge neutral">{genStatus ?? "…"}</span>
            </p>

            {outputs.length > 0 && (
              <>
                <p className="muted" style={{ fontSize: 12 }}>
                  レビュー・承認は <Link href="/review">Review</Link> 画面で行えます。
                </p>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 8 }}>
                  {outputs.map((o) => (
                    <OutputThumb key={o.id} output={o} />
                  ))}
                </div>
              </>
            )}
            {genStatus === "completed" && outputs.length === 0 && (
              <p className="muted">出力がありません。</p>
            )}
            {genStatus === "failed" && <p className="error">生成に失敗しました。</p>}
          </div>
        )}

        {error && <p className="error">{error}</p>}
      </div>

      <aside className="card">
        <h3>判定サマリ</h3>
        {check ? (
          <>
            <p>
              ステータス:{" "}
              <span className={`badge ${check.check_status}`}>{check.check_status}</span>
            </p>
            <p>{check.check_summary}</p>
            {check.required_approvals.length > 0 && (
              <p>必要承認: {check.required_approvals.join(" ・ ")}</p>
            )}
          </>
        ) : (
          <p className="muted">
            先に判定を実行してください。判定を通過しない限り生成できません。
          </p>
        )}
      </aside>
    </div>
  );
}

// Signed, short-lived, audited preview so the generated image is visible after a
// job completes (mock outputs return null and keep the placeholder box).
function OutputThumb({ output }: { output: Output }) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    api
      .getOutputPreview(output.id)
      .then((r) => setPreviewUrl(r.preview_url ? resolveFileUrl(r.preview_url) : null))
      .catch(() => setPreviewUrl(null));
  }, [output.id]);

  return (
    <div style={{ textAlign: "center" }}>
      {previewUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={previewUrl} alt="生成画像プレビュー" className="thumb" />
      ) : (
        <div className="thumb" />
      )}
      <div style={{ fontSize: 11 }} className="muted">
        {output.width ?? "?"}×{output.height ?? "?"}
      </div>
      <div style={{ fontSize: 11 }}>{output.output_status}</div>
    </div>
  );
}

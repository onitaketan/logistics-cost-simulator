"use client";

// Prompt template management (P1-004). Lists reusable prompt templates, creates new
// ones, and lets a user soft-disable/re-enable or delete them. All persistence and
// authorization is enforced by the backend — the UI just renders what it returns.

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { PromptTemplate } from "@/types";

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    api
      .listPromptTemplates()
      .then((t) => {
        setTemplates(t);
        setError(null);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  async function toggleActive(t: PromptTemplate) {
    setError(null);
    try {
      await api.updatePromptTemplate(t.id, { is_active: !t.is_active });
      setNotice(`${t.name} を${t.is_active ? "無効化" : "有効化"}しました。`);
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function remove(t: PromptTemplate) {
    if (!window.confirm(`テンプレート「${t.name}」を削除しますか？`)) return;
    setError(null);
    try {
      await api.deletePromptTemplate(t.id);
      setNotice(`${t.name} を削除しました。`);
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div>
      <h2>プロンプトテンプレート</h2>

      {error && <p className="error">{error}</p>}
      {notice && <p style={{ color: "var(--ok)" }}>{notice}</p>}

      <div className="card">
        <h3>テンプレート一覧</h3>
        {loading ? (
          <p className="muted">読み込み中…</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>名称</th><th>タグ</th><th>本文</th>
                <th>状態</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              {templates.map((t) => (
                <tr key={t.id}>
                  <td>{t.name}</td>
                  <td>{t.tags.length > 0 ? t.tags.join(", ") : "—"}</td>
                  <td className="muted" style={{ fontSize: 12 }}>
                    {t.body.length > 60 ? `${t.body.slice(0, 60)}…` : t.body}
                  </td>
                  <td>
                    {t.is_active ? (
                      <span className="badge ok">有効</span>
                    ) : (
                      <span className="badge ng">無効</span>
                    )}
                  </td>
                  <td>
                    {t.is_active ? (
                      <button className="ghost small" onClick={() => toggleActive(t)}>
                        無効化
                      </button>
                    ) : (
                      <button className="small" onClick={() => toggleActive(t)}>
                        有効化
                      </button>
                    )}{" "}
                    <button className="ghost small" onClick={() => remove(t)}>
                      削除
                    </button>
                  </td>
                </tr>
              ))}
              {templates.length === 0 && !error && (
                <tr><td colSpan={5} className="muted">テンプレートがありません。</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      <CreateTemplateForm
        onDone={() => { setNotice("テンプレートを作成しました。"); load(); }}
        onError={setError}
      />
    </div>
  );
}

function CreateTemplateForm({
  onDone,
  onError,
}: {
  onDone: () => void;
  onError: (m: string) => void;
}) {
  const [name, setName] = useState("");
  const [body, setBody] = useState("");
  const [negativeBody, setNegativeBody] = useState("");
  const [tags, setTags] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const parsedTags = tags
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      await api.createPromptTemplate({
        name,
        body,
        negative_body: negativeBody || undefined,
        tags: parsedTags.length > 0 ? parsedTags : undefined,
      });
      setName("");
      setBody("");
      setNegativeBody("");
      setTags("");
      onDone();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ maxWidth: 560 }}>
      <h3>テンプレートを作成</h3>
      <form onSubmit={submit}>
        <label className="field"><span>名称 *</span>
          <input value={name} onChange={(e) => setName(e.target.value)} required /></label>
        <label className="field"><span>本文 *</span>
          <textarea value={body} onChange={(e) => setBody(e.target.value)}
            required style={{ minHeight: 90 }} /></label>
        <label className="field"><span>ネガティブ本文</span>
          <textarea value={negativeBody} onChange={(e) => setNegativeBody(e.target.value)}
            style={{ minHeight: 50 }} /></label>
        <label className="field"><span>タグ（カンマ区切り）</span>
          <input value={tags} onChange={(e) => setTags(e.target.value)}
            placeholder="広告, 屋外, 高級感" /></label>
        <button type="submit" disabled={busy || !name || !body}>
          {busy ? "作成中…" : "テンプレート作成"}
        </button>
      </form>
    </div>
  );
}

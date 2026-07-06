"use client";

// Admin > User management (docs/02 §11). Lists users, creates users, and lets an
// admin suspend/activate or change a role. Authorization is enforced by the
// backend — non-admins get a 403 which we surface gracefully. The UI carries no
// permission logic of its own.

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Role } from "@rams/shared-types";
import type { User } from "@/types";

const ROLES: Role[] = ["admin", "legal", "sales", "creative", "approver", "viewer"];

export default function SettingsPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    api
      .listUsers()
      .then((u) => {
        setUsers(u);
        setError(null);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  async function changeStatus(u: User, status: string) {
    setError(null);
    try {
      await api.updateUser(u.id, { status });
      setNotice(`${u.name} を${status === "active" ? "有効化" : "停止"}しました。`);
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function changeRole(u: User, role: string) {
    setError(null);
    try {
      await api.updateUser(u.id, { role });
      setNotice(`${u.name} のロールを ${role} に変更しました。`);
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div>
      <h2>Settings — ユーザー管理</h2>

      {error && <p className="error">{error}（管理者権限が必要です）</p>}
      {notice && <p style={{ color: "var(--ok)" }}>{notice}</p>}

      <div className="card">
        <h3>ユーザー一覧</h3>
        {loading ? (
          <p className="muted">読み込み中…</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>氏名</th><th>メール</th><th>部署</th><th>ロール</th>
                <th>状態</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.name}</td>
                  <td>{u.email}</td>
                  <td>{u.department ?? "—"}</td>
                  <td>
                    <select value={u.role} onChange={(e) => changeRole(u, e.target.value)}>
                      {ROLES.map((r) => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                    </select>
                  </td>
                  <td>
                    {u.status === "active" ? (
                      <span className="badge ok">active</span>
                    ) : (
                      <span className="badge ng">{u.status}</span>
                    )}
                  </td>
                  <td>
                    {u.status === "active" ? (
                      <button className="ghost small" onClick={() => changeStatus(u, "suspended")}>
                        停止
                      </button>
                    ) : (
                      <button className="small" onClick={() => changeStatus(u, "active")}>
                        有効化
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {users.length === 0 && !error && (
                <tr><td colSpan={6} className="muted">ユーザーがいません。</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      <CreateUserForm onDone={() => { setNotice("ユーザーを作成しました。"); load(); }} onError={setError} />
    </div>
  );
}

function CreateUserForm({
  onDone,
  onError,
}: {
  onDone: () => void;
  onError: (m: string) => void;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<string>("viewer");
  const [department, setDepartment] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.createUser({
        name,
        email,
        password,
        role,
        department: department || undefined,
      });
      setName("");
      setEmail("");
      setPassword("");
      setDepartment("");
      setRole("viewer");
      onDone();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ maxWidth: 560 }}>
      <h3>ユーザーを作成</h3>
      <form onSubmit={submit}>
        <label className="field"><span>氏名 *</span>
          <input value={name} onChange={(e) => setName(e.target.value)} required /></label>
        <label className="field"><span>メール *</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <label className="field"><span>初期パスワード *</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        <div style={{ display: "flex", gap: 8 }}>
          <label className="field" style={{ flex: 1 }}><span>ロール</span>
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLES.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select></label>
          <label className="field" style={{ flex: 1 }}><span>部署</span>
            <input value={department} onChange={(e) => setDepartment(e.target.value)} /></label>
        </div>
        <button type="submit" disabled={busy || !name || !email || !password}>
          {busy ? "作成中…" : "ユーザー作成"}
        </button>
      </form>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { getToken, setAuth } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Already authenticated? Skip the form.
  useEffect(() => {
    if (getToken()) router.replace("/");
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await api.login(email, password, otp || undefined);
      setAuth(res.access_token, res.role);
      router.push("/");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 360, margin: "80px auto" }}>
      <div className="card">
        <h2>ログイン</h2>
        <p className="muted" style={{ fontSize: 13 }}>Real AI Model Studio 社内管理</p>
        <form onSubmit={submit}>
          <input placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)}
            style={{ width: "100%", padding: 8, marginBottom: 8 }} />
          <input type="password" placeholder="password" value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ width: "100%", padding: 8, marginBottom: 8 }} />
          <input placeholder="2FA code (任意)" value={otp} onChange={(e) => setOtp(e.target.value)}
            style={{ width: "100%", padding: 8, marginBottom: 12 }} />
          <button type="submit" style={{ width: "100%" }} disabled={busy}>
            {busy ? "認証中…" : "ログイン"}
          </button>
        </form>
        {error && <p className="error">{error}</p>}
      </div>
    </div>
  );
}

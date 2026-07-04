"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const res = await api.login(email, password, otp || undefined);
      window.localStorage.setItem("rams_token", res.access_token);
      router.push("/");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div style={{ maxWidth: 360, margin: "80px auto" }}>
      <div className="card">
        <h2>ログイン</h2>
        <form onSubmit={submit}>
          <input placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)}
            style={{ width: "100%", padding: 8, marginBottom: 8 }} />
          <input type="password" placeholder="password" value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ width: "100%", padding: 8, marginBottom: 8 }} />
          <input placeholder="2FA code (任意)" value={otp} onChange={(e) => setOtp(e.target.value)}
            style={{ width: "100%", padding: 8, marginBottom: 12 }} />
          <button type="submit" style={{ width: "100%" }}>ログイン</button>
        </form>
        {error && <p style={{ color: "var(--ng)" }}>{error}</p>}
      </div>
    </div>
  );
}

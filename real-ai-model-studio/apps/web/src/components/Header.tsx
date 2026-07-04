"use client";

// Top header: current role badge + logout. Logout tells the backend (best-effort)
// then clears local auth and returns to /login.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { clearAuth, getRole } from "@/lib/auth";

export function Header() {
  const router = useRouter();
  const [role, setRole] = useState<string | null>(null);

  useEffect(() => {
    setRole(getRole());
  }, []);

  async function logout() {
    try {
      await api.logout();
    } catch {
      // best-effort; local logout proceeds regardless
    }
    clearAuth();
    router.replace("/login");
  }

  return (
    <div className="app-header">
      <div style={{ fontSize: 13, color: "#556" }}>
        {role ? (
          <>
            ロール: <span className="badge role">{role}</span>
          </>
        ) : (
          "—"
        )}
      </div>
      <button className="ghost" onClick={logout}>
        ログアウト
      </button>
    </div>
  );
}

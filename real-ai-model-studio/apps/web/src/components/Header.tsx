"use client";

// Top header: current page title + role badge + logout. Logout tells the backend
// (best-effort) then clears local auth and returns to /login.

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { clearAuth, getRole } from "@/lib/auth";

const TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/models": "Models",
  "/projects": "Projects",
  "/generation": "Generation Studio",
  "/review": "Review",
  "/delivery": "Delivery",
  "/audit": "Audit Log",
  "/settings": "Settings",
};

function pageTitle(pathname: string): string {
  if (TITLES[pathname]) return TITLES[pathname];
  const base = `/${pathname.split("/")[1] ?? ""}`;
  return TITLES[base] ?? "Real AI Model Studio";
}

export function Header() {
  const router = useRouter();
  const pathname = usePathname();
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
      <strong style={{ fontSize: "var(--fs-lg)" }}>{pageTitle(pathname)}</strong>
      <div className="header-user">
        <span>
          ロール:{" "}
          <span className={`badge ${role ? "role" : "neutral"}`}>{role ?? "未ログイン"}</span>
        </span>
        <button className="ghost small" onClick={logout}>
          ログアウト
        </button>
      </div>
    </div>
  );
}

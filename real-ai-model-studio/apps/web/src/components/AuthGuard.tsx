"use client";

// Client-side route guard. If there is no token in localStorage, redirect to
// /login. This is defense-in-depth UI only: the backend rejects unauthenticated
// requests regardless. Renders nothing until the check resolves to avoid a flash
// of protected content.
//
// AUTO-LOGIN (pre-launch, single-operator PCs): when NEXT_PUBLIC_AUTO_LOGIN is
// "true", a missing token triggers an automatic login with the seeded admin
// credentials instead of bouncing to /login. The backend auth stack is fully
// intact — this merely performs the same login call the form would; every action
// is still authenticated and audited as the admin user. If the credentials were
// rotated (or the API is down) it falls back to the normal login page.
// LAUNCH CHECKLIST: build with NEXT_PUBLIC_AUTO_LOGIN=false (see README).

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { getToken, setAuth } from "@/lib/auth";

const AUTO_LOGIN = process.env.NEXT_PUBLIC_AUTO_LOGIN === "true";
const DEFAULT_EMAIL = "admin@example.com";
const DEFAULT_PASSWORD = "ChangeMe123!";

export function AuthGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (getToken()) {
      setReady(true);
      return;
    }
    if (!AUTO_LOGIN) {
      router.replace("/login");
      return;
    }
    let cancelled = false;
    api
      .login(DEFAULT_EMAIL, DEFAULT_PASSWORD)
      .then((r) => {
        if (cancelled) return;
        setAuth(r.access_token, r.role);
        setReady(true);
      })
      .catch(() => {
        if (!cancelled) router.replace("/login");
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (!ready) {
    return <p style={{ color: "#889" }}>認証を確認しています…</p>;
  }
  return <>{children}</>;
}

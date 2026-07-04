"use client";

// Client-side route guard. If there is no token in localStorage, redirect to
// /login. This is defense-in-depth UI only: the backend rejects unauthenticated
// requests regardless. Renders nothing until the check resolves to avoid a flash
// of protected content.

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/auth";

export function AuthGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setReady(true);
  }, [router]);

  if (!ready) {
    return <p style={{ color: "#889" }}>認証を確認しています…</p>;
  }
  return <>{children}</>;
}

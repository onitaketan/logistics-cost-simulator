"use client";

// App frame. The /login route and the external /portal/* approval pages render
// bare (no sidebar/header/guard) — portal visitors have no session. Every other
// route gets the sidebar + header and is wrapped in the AuthGuard.

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Sidebar } from "@/components/Sidebar";
import { Header } from "@/components/Header";
import { AuthGuard } from "@/components/AuthGuard";

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  if (pathname === "/login" || pathname.startsWith("/portal")) {
    return <>{children}</>;
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main">
        <Header />
        <AuthGuard>{children}</AuthGuard>
      </main>
    </div>
  );
}

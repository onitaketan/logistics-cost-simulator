"use client";

// App frame. The /login route renders bare (no sidebar/header/guard); every other
// route gets the sidebar + header and is wrapped in the AuthGuard.

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Sidebar } from "@/components/Sidebar";
import { Header } from "@/components/Header";
import { AuthGuard } from "@/components/AuthGuard";

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  if (pathname === "/login") {
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

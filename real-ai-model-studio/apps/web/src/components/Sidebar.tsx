"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  ["/", "Dashboard"],
  ["/models", "Models"],
  ["/projects", "Projects"],
  ["/generation", "Generation Studio"],
  ["/compliance", "コンプライアンス"],
  ["/review", "Review"],
  ["/delivery", "Delivery"],
  ["/audit", "Audit Log"],
  ["/settings", "Settings"],
] as const;

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar() {
  const pathname = usePathname();

  return (
    <nav className="app-sidebar" aria-label="メインナビゲーション">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">
          AI
        </span>
        <h1>Real AI Model Studio</h1>
      </div>
      <div className="nav-group">
        {NAV.map(([href, label]) => {
          const active = isActive(pathname, href);
          return (
            <Link
              key={href}
              href={href}
              className={active ? "active" : undefined}
              aria-current={active ? "page" : undefined}
            >
              {label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

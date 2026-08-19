"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { getRole } from "@/lib/auth";

type NavItem = readonly [href: string, label: string];

type Section = {
  readonly title: string;
  readonly items: readonly NavItem[];
};

const SECTIONS: readonly Section[] = [
  {
    title: "ホーム",
    items: [["/", "ダッシュボード"]],
  },
  {
    title: "制作フロー",
    items: [
      ["/models", "モデル管理"],
      ["/projects", "案件管理"],
      ["/generation", "生成スタジオ"],
      ["/review", "レビュー・承認"],
      ["/compare", "出力比較"],
      ["/delivery", "納品"],
    ],
  },
  {
    title: "ツール",
    items: [
      ["/templates", "プロンプトテンプレート"],
      ["/compliance", "判定チェック"],
    ],
  },
] as const;

// 管理 section is filtered by role below. This visibility is a UI mirror only —
// the backend enforces the real access control; hiding links here is purely a
// convenience so users don't see menus they can't use.
const ADMIN_SECTION_TITLE = "管理";
const ADMIN_ITEMS: readonly (readonly [href: string, label: string, roles: readonly string[]])[] = [
  ["/audit", "監査ログ", ["admin", "legal"]],
  ["/settings", "ユーザー管理", ["admin"]],
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar() {
  const pathname = usePathname();
  // Hydration-safe role read (same pattern as Header): role stays null on the
  // server and on first client paint, then is filled in after mount. While role
  // is null we render WITHOUT the 管理 section so no menu flashes and disappears.
  const [role, setRole] = useState<string | null>(null);

  useEffect(() => {
    setRole(getRole());
  }, []);

  const adminItems = role
    ? ADMIN_ITEMS.filter(([, , roles]) => roles.includes(role))
    : [];

  const sections: readonly Section[] =
    adminItems.length > 0
      ? [
          ...SECTIONS,
          {
            title: ADMIN_SECTION_TITLE,
            items: adminItems.map(([href, label]) => [href, label] as const),
          },
        ]
      : SECTIONS;

  return (
    <nav className="app-sidebar" aria-label="メインナビゲーション">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">
          AI
        </span>
        <h1>Real AI Model Studio</h1>
      </div>
      {sections.map((section) => (
        <div className="nav-group" key={section.title}>
          <div className="nav-section-title">{section.title}</div>
          {section.items.map(([href, label]) => {
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
      ))}
    </nav>
  );
}

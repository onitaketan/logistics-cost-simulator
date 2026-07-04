import Link from "next/link";

const NAV = [
  ["/", "Dashboard"],
  ["/models", "Models"],
  ["/projects", "Projects"],
  ["/generation", "Generation Studio"],
  ["/review", "Review"],
  ["/delivery", "Delivery"],
  ["/audit", "Audit Log"],
  ["/settings", "Settings"],
] as const;

export function Sidebar() {
  return (
    <nav className="app-sidebar">
      <h1>Real AI Model Studio</h1>
      {NAV.map(([href, label]) => (
        <Link key={href} href={href}>
          {label}
        </Link>
      ))}
    </nav>
  );
}

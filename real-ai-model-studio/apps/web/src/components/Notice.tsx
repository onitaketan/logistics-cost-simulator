// Reusable inline notice/banner. Variant drives colour + icon.

import type { ReactNode } from "react";

type Variant = "info" | "success" | "error";

const ICON: Record<Variant, string> = {
  info: "ℹ️",
  success: "✓",
  error: "⚠️",
};

export function Notice({
  variant = "info",
  children,
}: {
  variant?: Variant;
  children: ReactNode;
}) {
  return (
    <div className={`notice ${variant}`} role={variant === "error" ? "alert" : "status"}>
      <span className="notice-icon" aria-hidden="true">
        {ICON[variant]}
      </span>
      <div>{children}</div>
    </div>
  );
}

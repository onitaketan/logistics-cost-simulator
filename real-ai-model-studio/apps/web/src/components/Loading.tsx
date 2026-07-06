// Reusable loading indicator: an accessible spinner with an optional label.

export function Loading({ label = "読み込み中…" }: { label?: string }) {
  return (
    <div className="loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

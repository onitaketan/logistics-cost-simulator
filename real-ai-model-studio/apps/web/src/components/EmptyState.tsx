// Reusable empty-state placeholder: an icon/emoji plus a short message.

export function EmptyState({
  icon = "📭",
  message,
}: {
  icon?: string;
  message: string;
}) {
  return (
    <div className="empty">
      <div className="empty-icon" aria-hidden="true">
        {icon}
      </div>
      <div className="empty-msg">{message}</div>
    </div>
  );
}

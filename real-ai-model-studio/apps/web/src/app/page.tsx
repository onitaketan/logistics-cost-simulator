// Dashboard (docs/02 §4). KPI cards + attention tables. Data wiring is TODO —
// this scaffold renders the layout with placeholder figures.

const KPIS = [
  ["Active Models", "—"],
  ["Projects In Progress", "—"],
  ["Pending Approvals", "—"],
  ["High Risk Items", "—"],
  ["Expiring Contracts", "—"],
];

export default function Dashboard() {
  return (
    <div>
      <h2>Dashboard</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12 }}>
        {KPIS.map(([label, value]) => (
          <div className="card" key={label}>
            <div style={{ fontSize: 12, color: "#667" }}>{label}</div>
            <div style={{ fontSize: 28, fontWeight: 700 }}>{value}</div>
          </div>
        ))}
      </div>
      <div className="card">
        <h3>Contracts expiring within 30 days</h3>
        <p style={{ color: "#889" }}>TODO: /audit-logs と契約データを結線</p>
      </div>
    </div>
  );
}

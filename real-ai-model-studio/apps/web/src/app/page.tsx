"use client";

// Dashboard (docs/02 §4). Real counts derived from /models and /projects, plus a
// project table. The UI only reflects backend data; it computes no compliance.

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Model, Project } from "@rams/shared-types";

export default function Dashboard() {
  const [models, setModels] = useState<Model[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.listModels(), api.listProjects()])
      .then(([m, p]) => {
        setModels(m);
        setProjects(p);
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  const activeModels = models.filter((m) => m.status !== "suspended").length;
  const inProgress = projects.filter((p) =>
    ["draft", "generating", "review"].includes(p.project_status),
  ).length;
  const pendingApprovals = projects.filter((p) => p.project_status === "review").length;
  const highRisk = projects.filter(
    (p) => p.risk_level === "high" || p.risk_level === "prohibited",
  ).length;

  const kpis: [string, string | number][] = [
    ["Active Models", activeModels],
    ["Projects In Progress", inProgress],
    ["Pending Approvals", pendingApprovals],
    ["High Risk Items", highRisk],
    ["Registered Models", models.length],
  ];

  return (
    <div>
      <h2>Dashboard</h2>
      {error && <p className="error">{error}</p>}

      <div className="kpi-grid">
        {kpis.map(([label, value]) => (
          <div className="card" key={label}>
            <div className="kpi-label">{label}</div>
            <div className="kpi-value">{value}</div>
          </div>
        ))}
      </div>

      <div className="card">
        <h3>案件一覧</h3>
        <table>
          <thead>
            <tr>
              <th>案件名</th>
              <th>クライアント</th>
              <th>状態</th>
              <th>リスク</th>
              <th>納期</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {projects.map((p) => (
              <tr key={p.id}>
                <td>{p.project_name}</td>
                <td>{p.client_name ?? "—"}</td>
                <td>{p.project_status}</td>
                <td>{p.risk_level ?? "—"}</td>
                <td>{p.deadline ?? "—"}</td>
                <td>
                  <Link href={`/projects/${p.id}`}>詳細</Link>
                </td>
              </tr>
            ))}
            {projects.length === 0 && !error && (
              <tr>
                <td colSpan={6} className="muted">案件がありません。</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

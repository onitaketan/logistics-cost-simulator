"use client";

// Dashboard (docs/02 §4). Real counts derived from /models and /projects, plus a
// project table. The UI only reflects backend data; it computes no compliance.

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Loading } from "@/components/Loading";
import { Notice } from "@/components/Notice";
import { EmptyState } from "@/components/EmptyState";
import type { ExpiringContract } from "@/types";
import type { Model, Project } from "@rams/shared-types";

export default function Dashboard() {
  const [models, setModels] = useState<Model[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [expiring, setExpiring] = useState<ExpiringContract[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.listModels(), api.listProjects(), api.expiringContracts(30)])
      .then(([m, p, e]) => {
        setModels(m);
        setProjects(p);
        setExpiring(e);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
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
    ["Expiring Contracts", expiring.length],
  ];

  if (loading) {
    return (
      <div>
        <h2>Dashboard</h2>
        <div className="card">
          <Loading label="ダッシュボードを読み込んでいます…" />
        </div>
      </div>
    );
  }

  return (
    <div>
      <h2>Dashboard</h2>
      {error && <Notice variant="error">データの取得に失敗しました: {error}</Notice>}

      <div className="kpi-grid">
        {kpis.map(([label, value]) => (
          <div className="card" key={label}>
            <div className="kpi-label">{label}</div>
            <div className="kpi-value">{value}</div>
          </div>
        ))}
      </div>

      <div className="card">
        <h3>契約期限 (30日以内)</h3>
        {expiring.length === 0 ? (
          !error && <EmptyState icon="🗓️" message="期限が近い契約はありません。" />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>芸名</th>
                  <th>契約番号</th>
                  <th>終了日</th>
                  <th>残日数</th>
                </tr>
              </thead>
              <tbody>
                {expiring.map((c) => (
                  <tr key={c.contract_id}>
                    <td>{c.stage_name}</td>
                    <td>{c.contract_number}</td>
                    <td>{c.contract_end}</td>
                    <td>
                      <span className={`pill ${c.days_left <= 7 ? "ng" : "warn"}`}>
                        {c.days_left}日
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h3>案件一覧</h3>
        {projects.length === 0 ? (
          !error && <EmptyState icon="📁" message="案件がありません。" />
        ) : (
          <div className="table-scroll">
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
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

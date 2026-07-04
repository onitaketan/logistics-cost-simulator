"use client";

// Project list (docs/02 §7). Link into detail; create via /projects/new.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Project } from "@rams/shared-types";

export default function ProjectsPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listProjects().then(setProjects).catch((e) => setError((e as Error).message));
  }, []);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2>Projects</h2>
        <button onClick={() => router.push("/projects/new")}>新規案件作成</button>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>案件名</th>
              <th>クライアント</th>
              <th>カテゴリ</th>
              <th>状態</th>
              <th>リスク</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {projects.map((p) => (
              <tr key={p.id}>
                <td>{p.project_name}</td>
                <td>{p.client_name ?? "—"}</td>
                <td>{p.product_category ?? "—"}</td>
                <td>{p.project_status}</td>
                <td>{p.risk_level ?? "—"}</td>
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

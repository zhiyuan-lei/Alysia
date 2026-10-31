import React from "react";
import {
  Activity, AlertTriangle, BarChart3, BookOpen, Bot, Boxes, CheckCircle2,
  ChevronRight, ClipboardCheck, Cpu, FileText, Gauge, LayoutDashboard,
  ListVideo, MemoryStick, Network, Play, RefreshCw, ShieldCheck, Sparkles,
  Workflow, XCircle,
} from "lucide-react";
import { zh, zhStatus } from "./zh";

export const NAV = [
  ["dashboard", "总览", LayoutDashboard], ["runs", "运行记录", ListVideo],
  ["supervisor", "目标监督", Network], ["studio", "工作室", Bot],
  ["production", "制作", Gauge], ["visual", "画面生成", Sparkles],
  ["local-create", "本地创作", Play],
  ["knowledge", "知识库", BookOpen], ["intelligence", "分析与记忆", BarChart3],
  ["creator-jobs", "创作者 Beta", FileText],
  ["approvals", "审批", ClipboardCheck], ["skills", "技能", Boxes],
  ["audit", "审计", ShieldCheck],
];

export function Shell({ route, onNavigate, children, refreshedAt }) {
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">A</span><span><strong>Alysia</strong><small>本地控制中心</small></span></div>
      <nav>{NAV.map(([id, label, Icon]) => <button key={id} className={route === id ? "active" : ""} onClick={() => onNavigate(id)}><Icon size={18}/><span>{label}</span></button>)}</nav>
      <div className="local-note"><span className="dot healthy"/>仅限本机<small>127.0.0.1</small></div>
    </aside>
    <div className="workspace">
      <header><div className="local-chip"><Cpu size={16}/>本地控制台</div><div className="refresh"><RefreshCw size={15}/>上次刷新：{refreshedAt || "—"}</div></header>
      <main>{children}</main>
    </div>
  </div>;
}

export function PageHeader({ title, subtitle, actions }) {
  return <div className="page-header"><div><h1>{zh(title)}</h1>{subtitle ? <p>{zh(subtitle)}</p> : null}</div>{actions ? <div className="page-actions">{actions}</div> : null}</div>;
}

export function Panel({ title, action, children, className = "" }) {
  return <section className={`panel ${className}`}><div className="panel-heading"><h2>{zh(title)}</h2>{action}</div><div className="panel-body">{children}</div></section>;
}

export function Status({ value, label }) {
  const normalized = String(value || "unknown").toLowerCase().replaceAll("_", "-");
  const Icon = ["pass", "healthy", "completed", "safe", "secure", "allow", "submitted", "available"].some((item) => normalized.includes(item)) ? CheckCircle2 : ["fail", "blocked", "deny", "error", "unavailable"].some((item) => normalized.includes(item)) ? XCircle : AlertTriangle;
  return <span className={`status status-${normalized}`}><Icon size={14}/>{zh(label) || zhStatus(value)}</span>;
}

export function Loading({ label = "Loading" }) { return <div className="state loading"><Activity size={20}/>{zh(label)}…</div>; }
export function ErrorState({ message }) { return <div className="state error"><AlertTriangle size={20}/><span>{zh(message)}</span></div>; }
export function Empty({ label = "No data available" }) { return <div className="state empty"><FileText size={20}/>{zh(label)}</div>; }

export function DataTable({ columns, rows, onRow, empty = "No records" }) {
  if (!rows?.length) return <Empty label={empty}/>;
  return <div className="table-wrap"><table><thead><tr>{columns.map((column) => <th key={column.key}>{zh(column.label)}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={row.id || row.run_id || row.event_id || index} onClick={() => onRow?.(row)} className={onRow ? "clickable" : ""}>{columns.map((column) => <td key={column.key}>{column.render ? column.render(row[column.key], row) : ["stage", "milestone", "category"].includes(column.key) ? zhStatus(row[column.key] ?? "—") : String(row[column.key] ?? "—")}</td>)}</tr>)}</tbody></table></div>;
}

export function Timeline({ items = [] }) {
  return <div className="timeline">{items.map((item, index) => <div className={`timeline-item timeline-${item.status}`} key={item.label}><div className="timeline-node">{item.status === "completed" ? "✓" : index + 1}</div><div><strong>{zh(item.label)}</strong><small>{zhStatus(item.status)}</small></div>{index < items.length - 1 ? <ChevronRight className="timeline-arrow" size={16}/> : null}</div>)}</div>;
}

export function MetricBar({ label, used, total, unit = "MB" }) {
  const percent = total ? Math.min(100, Math.round((used / total) * 100)) : 0;
  return <div className="metric"><div><span>{zh(label)}</span><strong>{used ?? "—"} / {total ?? "—"} {unit}</strong></div><div className="bar"><span style={{ width: `${percent}%` }}/></div></div>;
}

export function ActionButton({ children, danger = false, secondary = false, ...props }) {
  return <button className={`action-button ${danger ? "danger" : ""} ${secondary ? "secondary" : ""}`} {...props}>{children}</button>;
}

export function EnvironmentLabel({ value }) {
  return <span className={`environment environment-${String(value).toLowerCase()}`}>{zhStatus(value)}（{value}）</span>;
}

export { MemoryStick, Play, Workflow };

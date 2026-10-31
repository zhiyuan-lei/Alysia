import React, { useEffect, useState } from "react";
import { Shell } from "./components";
import { LocalCreatePage } from "./local-create";
import { ApprovalsPage, AuditPage, CreatorJobsPage, DashboardPage, IntelligencePage, KnowledgePage, ProductionPage, RunDetailPage, RunsPage, SkillsPage, StudioPage, SupervisorPage, VisualPage } from "./pages";

function routeFromHash() {
  return window.location.hash.replace(/^#\/?/, "") || "dashboard";
}

export function App() {
  const [route, setRoute] = useState(routeFromHash);
  const [refreshedAt, setRefreshedAt] = useState(new Date().toLocaleTimeString());
  useEffect(() => { const listener=()=>setRoute(routeFromHash()); window.addEventListener("hashchange",listener); return ()=>window.removeEventListener("hashchange",listener); },[]);
  function navigate(next) { window.location.hash = `/${next}`; setRoute(next); setRefreshedAt(new Date().toLocaleTimeString()); }
  const [root,...parts]=route.split("/");
  const page = root === "runs" && parts[0] ? <RunDetailPage runId={parts[0]}/> : ({
    dashboard:<DashboardPage onNavigate={navigate}/>, runs:<RunsPage onNavigate={navigate}/>, supervisor:<SupervisorPage/>, studio:<StudioPage/>, production:<ProductionPage/>, visual:<VisualPage/>, "local-create":<LocalCreatePage/>, knowledge:<KnowledgePage/>, intelligence:<IntelligencePage/>, "creator-jobs":<CreatorJobsPage/>, approvals:<ApprovalsPage/>, skills:<SkillsPage/>, audit:<AuditPage/>,
  }[root] || <DashboardPage onNavigate={navigate}/>);
  return <Shell route={root} onNavigate={navigate} refreshedAt={refreshedAt}>{page}</Shell>;
}

import React, { useMemo, useState } from "react";
import { AlertTriangle, Check, Eye, Play, RotateCcw, ShieldCheck, X } from "lucide-react";
import { apiGet, apiGetText, apiPost, safeArtifactUrl } from "./api";
import { useApi } from "./hooks";
import { ActionButton, DataTable, Empty, EnvironmentLabel, ErrorState, Loading, MetricBar, PageHeader, Panel, Status, Timeline } from "./components";
import { zh } from "./zh";

function Guarded({ state, children }) {
  if (state.loading) return <Loading/>;
  if (state.error) return <ErrorState message={state.error}/>;
  return children(state.data);
}

export function DashboardPage({ onNavigate }) {
  const dashboard = useApi("/api/dashboard");
  return <><PageHeader title="Dashboard" subtitle="Alysia 的本地运行、门禁与资源状态。"/>
    <Guarded state={dashboard}>{(data) => {
      const resources = data.resources || {};
      const vram = resources.gpu || {};
      const ram = resources.ram || {};
      const h3 = data.providers?.find((provider) => provider.provider_id === "visual.comfyui-h3");
      const evalGate = data.health?.alpha18 || {};
      return <div className="dashboard-grid">
        <Panel title="System status" className="system-panel"><div className="status-list">
          <div><span>ComfyUI / MiniMax H3</span><Status value={h3?.health_status}/></div>
          <div><span>服务提供方</span><Status value={data.providers?.some((item) => item.health_status === "unavailable") ? "warning" : "healthy"}/></div>
          <div><span>Alpha18 评估</span><Status value={evalGate.status}/></div>
          <div><span>Alpha19 可靠性</span><Status value={data.health?.alpha19?.open ? "warning" : "pass"}/></div>
          <div><span>Alpha20 安全</span><Status value={data.health?.alpha20?.enabled ? "secure" : "blocked"}/></div>
        </div></Panel>
        <Panel title="Resource guard"><MetricBar label="RTX 4060 Ti VRAM" used={vram.used_mb} total={vram.budget_mb || vram.total_mb}/><MetricBar label="System RAM budget" used={ram.used_mb} total={ram.budget_mb || ram.total_mb}/><p className="muted">检测到的物理内存：{ram.total_mb ?? "—"} MB</p><div className="disk-line"><span>磁盘可用空间</span><strong>{resources.disk?.free_gb ?? "—"} GB</strong></div><Status value={resources.guard?.status}/></Panel>
        <Panel title="Pending approvals" action={<button className="text-link" onClick={() => onNavigate("approvals")}>查看全部</button>}><div className="big-number">{data.approvals?.length || 0}</div><p className="muted">敏感动作仍由 Alpha20 对范围、哈希和版本重新校验。</p></Panel>
        <Panel title="Active runs" className="span-2"><DataTable rows={(data.runs || []).filter((run) => run.status !== "completed").slice(0, 6)} columns={[{key:"run_id",label:"Run"},{key:"topic",label:"Topic"},{key:"stage",label:"Stage"},{key:"status",label:"Status",render:(value)=><Status value={value}/>},{key:"updated_at",label:"Updated"}]} onRow={(row)=>onNavigate(`runs/${row.run_id}`)} empty="No active runs"/></Panel>
        <Panel title="Recent failures"><DataTable rows={data.errors || []} columns={[{key:"run_id",label:"Run"},{key:"stage",label:"Stage"},{key:"category",label:"Failure"},{key:"status",label:"Status",render:(value)=><Status value={value}/>}]} empty="No recent failures"/></Panel>
        <Panel title="Evaluation gate" className="span-3"><div className="gate-summary"><div><Status value={evalGate.status}/><strong>{evalGate.status === "BLOCKED" ? "晋级受阻" : "无严重回归"}</strong></div><p>{evalGate.blocking_findings?.length || 0} 项阻塞发现 · 此页面只读，不能覆盖门禁决定。</p></div></Panel>
      </div>;
    }}</Guarded>
  </>;
}

export function RunsPage({ onNavigate }) {
  const runs = useApi("/api/runs");
  const [filter, setFilter] = useState("all");
  return <><PageHeader title="Runs" subtitle="检查真实任务状态、里程碑和恢复入口。" actions={<select value={filter} onChange={(event)=>setFilter(event.target.value)}><option value="all">全部状态</option><option value="running">运行中</option><option value="failed">失败</option><option value="waiting_approval">等待审批</option></select>}/>
    <Panel title="Run inventory"><Guarded state={runs}>{(data)=><DataTable rows={data.filter((run)=>filter === "all" || run.status === filter)} columns={[{key:"run_id",label:"Run ID"},{key:"topic",label:"Topic"},{key:"stage",label:"Stage"},{key:"milestone",label:"Milestone"},{key:"testing",label:"Provenance",render:(value)=><EnvironmentLabel value={value ? "MOCK" : "REAL"}/>},{key:"status",label:"Status",render:(value)=><Status value={value}/>}]} onRow={(row)=>onNavigate(`runs/${row.run_id}`)} empty="No matching runs"/>}</Guarded></Panel>
  </>;
}

function ArtifactPreview({ artifact }) {
  const url = safeArtifactUrl(artifact?.url);
  if (!artifact) return <Empty label="Select an artifact"/>;
  if (!url) return <ErrorState message="Unsafe or unsupported artifact URL"/>;
  if (artifact.kind === "video") return <video className="media-preview" controls src={url}/>;
  if (artifact.kind === "image") return <img className="media-preview" src={url} alt={artifact.name}/>;
  if (artifact.kind === "audio") return <audio controls src={url}/>;
  return <TextArtifact url={url}/>;
}

function TextArtifact({ url }) {
  const [state,setState]=useState({data:null,loading:true,error:null});
  React.useEffect(()=>{let active=true;apiGetText(url).then((data)=>active&&setState({data,loading:false,error:null})).catch((error)=>active&&setState({data:null,loading:false,error:error.message}));return()=>{active=false};},[url]);
  return <Guarded state={state}>{(data)=><pre className="artifact-text">{data}</pre>}</Guarded>;
}

export function RunDetailPage({ runId }) {
  const detail = useApi(`/api/runs/${runId}`);
  const artifacts = useApi(`/api/runs/${runId}/artifacts`);
  const [selected, setSelected] = useState(null);
  const [diagnosis, setDiagnosis] = useState(null);
  const [notice, setNotice] = useState(null);
  const [confirm, setConfirm] = useState(null);
  async function diagnose() { setDiagnosis(await apiGet(`/api/runs/${runId}/diagnose`)); }
  async function action(kind) {
    try { const result = await apiPost(`/api/runs/${runId}/${kind}`, { confirmed: true, failure_id: diagnosis?.failures?.at(-1)?.failure_id || null }); setNotice(`${kind === "resume" ? "继续" : "恢复"}已完成：${result.milestone || result.decision?.action || "成功"}`); setConfirm(null); }
    catch (error) { setNotice(error.message); setConfirm(null); }
  }
  return <><Guarded state={detail}>{(data)=><>
    <PageHeader title="Run detail" subtitle={`${data.summary.run_id} · ${data.summary.topic}`} actions={<><EnvironmentLabel value={data.summary.testing ? "MOCK" : "REAL"}/><Status value={data.summary.status}/></>}/>
    <Panel title="Stage timeline"><Timeline items={data.timeline}/></Panel>
    <div className="detail-grid">
      <Panel title="Artifacts" className="artifact-panel"><Guarded state={artifacts}>{(items)=>{ const current = selected || items.find((item)=>["final_video","publish_cover","script","storyboard"].includes(item.key)) || items[0]; return <div className="artifact-layout"><div className="artifact-list">{items.filter((item)=>item.previewable).map((item)=><button className={current?.key===item.key?"selected":""} key={item.key} onClick={()=>setSelected(item)}><span>{item.key}</span><small>{Math.ceil(item.size/1024)} KB</small></button>)}</div><div className="artifact-preview"><ArtifactPreview artifact={current}/></div></div>;}}</Guarded></Panel>
      <Panel title="Diagnose & recovery"><div className="recovery-actions"><ActionButton secondary onClick={diagnose}>诊断</ActionButton><ActionButton secondary onClick={()=>setConfirm("resume")}><Play size={15}/>继续</ActionButton><ActionButton onClick={()=>setConfirm("recover")}><RotateCcw size={15}/>恢复</ActionButton></div>{diagnosis ? <div className="diagnosis"><Status value={diagnosis.resource_guard?.status}/><p>{diagnosis.failures?.at(-1)?.suggested_action || "暂无待处理故障建议。"}</p><small>恢复轮次：{diagnosis.failures?.at(-1)?.recovery_round ?? 0}</small></div> : <Empty label="Run Diagnose to inspect FailureRecord and integrity"/>}{notice ? <div className="notice">{notice}</div> : null}</Panel>
    </div>
    {confirm ? <ConfirmDialog title={`确认${confirm === "resume" ? "继续" : "恢复"}`} message="此操作受 Alpha19 恢复策略约束，不能强制忽略完整性检查。" onCancel={()=>setConfirm(null)} onConfirm={()=>action(confirm)}/> : null}
  </>}</Guarded></>;
}

function useMulti(paths) {
  const key = paths.join("|");
  const [state, setState] = useState({loading:true,data:null,error:null});
  React.useEffect(()=>{ let active=true; setState({loading:true,data:null,error:null}); Promise.all(paths.map(apiGet)).then((values)=>active&&setState({loading:false,data:values,error:null})).catch((error)=>active&&setState({loading:false,data:null,error:error.message})); return ()=>{active=false}; },[key]);
  return state;
}

export function SupervisorPage() {
  const state = useMulti(["/api/supervisor/goals","/api/supervisor/plans","/api/supervisor/blockers"]);
  return <><PageHeader title="Supervisor" subtitle="长期目标、计划和阻塞；默认只读。"/><Guarded state={state}>{([goals,plans,blockers])=><div className="two-column"><Panel title="Goals"><DataTable rows={goals} columns={[{key:"title",label:"Goal"},{key:"status",label:"Status",render:(v)=><Status value={v}/>},{key:"priority",label:"Priority"}]} empty="No goals"/></Panel><Panel title="Blockers"><pre className="artifact-text compact">{JSON.stringify(blockers,null,2)}</pre></Panel><Panel title="Long-horizon plans" className="span-2"><DataTable rows={plans} columns={[{key:"plan_id",label:"Plan"},{key:"goal_id",label:"Goal"},{key:"status",label:"Status",render:(v)=><Status value={v}/>}]} empty="No plans"/></Panel></div>}</Guarded></>;
}

function RunScopedPage({ title, subtitle, endpoints, render }) {
  const runs = useApi("/api/runs");
  return <><PageHeader title={title} subtitle={subtitle}/><Guarded state={runs}>{(items)=>{ const run=items[0]; if(!run)return <Empty label="No runs available"/>; return <RunScopedData run={run} endpoints={endpoints} render={render}/>; }}</Guarded></>;
}

function RunScopedData({ run, endpoints, render }) { const state=useMulti(endpoints.map((path)=>path.replace(":run",run.run_id))); return <Guarded state={state}>{(data)=>render(run,data)}</Guarded>; }

export function StudioPage(){return <RunScopedPage title="Studio" subtitle="Agent ownership、handoff 与 trace。" endpoints={["/api/studio/:run/agents","/api/studio/:run/trace"]} render={(run,[agents,trace])=><div className="two-column"><Panel title="Agents"><DataTable rows={agents} columns={[{key:"agent_id",label:"Agent"},{key:"role",label:"Role"},{key:"artifact_ownership",label:"Ownership",render:(v)=>Array.isArray(v)?v.join(", "):v}]} empty="No registered agents"/></Panel><Panel title={`执行轨迹 · ${run.run_id}`}><DataTable rows={trace} columns={[{key:"at",label:"Time"},{key:"agent_id",label:"Agent"},{key:"action",label:"Action"},{key:"status",label:"Status",render:(v)=><Status value={v}/>}]} empty="No studio trace"/></Panel></div>}/>}

export function ProductionPage(){return <RunScopedPage title="Production" subtitle="Provider routing、资源估计和 fallback。" endpoints={["/api/production/:run/plan","/api/production/:run/resources"]} render={(run,[plan,resources])=><div className="two-column"><Panel title={`制作计划 · ${run.run_id}`}><pre className="artifact-text">{JSON.stringify(plan,null,2)}</pre></Panel><Panel title="Observed resources"><pre className="artifact-text">{JSON.stringify(resources,null,2)}</pre></Panel></div>}/>}

export function VisualPage(){const jobs=useApi("/api/visual/jobs"); const dash=useApi("/api/dashboard"); return <><PageHeader title="Visual" subtitle="受控 H3/ComfyUI 队列与健康状态；不提供 workflow shell。"/><div className="two-column"><Panel title="ComfyUI / H3 health"><Guarded state={dash}>{(d)=>{const h3=d.providers.find((p)=>p.provider_id==="visual.comfyui-h3");return <><Status value={h3?.health_status}/><p className="muted">{h3?.health_details||"No health details"}</p></>;}}</Guarded></Panel><Panel title="Job queue"><Guarded state={jobs}>{(data)=><DataTable rows={data} columns={[{key:"job_id",label:"Job"},{key:"run_id",label:"Run"},{key:"status",label:"Status",render:(v)=><Status value={v}/>},{key:"provider",label:"Provider"}]} empty="No H3 jobs queued"/>}</Guarded></Panel></div></>}

export function KnowledgePage(){const state=useMulti(["/api/knowledge/status","/api/knowledge/claims","/api/knowledge/conflicts","/api/knowledge/stale"]);return <><PageHeader title="Knowledge" subtitle="Claim、来源、冲突和时效性。"/><Guarded state={state}>{([status,claims,conflicts,stale])=><div className="two-column"><Panel title="Knowledge status"><pre className="artifact-text compact">{JSON.stringify(status,null,2)}</pre></Panel><Panel title="Grounding warnings"><p>{conflicts.length} 项冲突 · {stale.length} 项过期主张</p>{conflicts.length||stale.length?<Status value="warning"/>:<Status value="healthy"/>}</Panel><Panel title="Claims" className="span-2"><DataTable rows={claims} columns={[{key:"claim_id",label:"Claim"},{key:"topic",label:"Topic"},{key:"statement",label:"Statement"},{key:"status",label:"Status",render:(v)=><Status value={v}/>}]} empty="No claims"/></Panel></div>}</Guarded></>}

export function IntelligencePage(){const state=useMulti(["/api/memory/lessons","/api/experiments"]);return <><PageHeader title="Analytics / Memory / Experiments" subtitle="真实、模拟和测试来源保持显式隔离。"/><Guarded state={state}>{([lessons,experiments])=><div className="two-column"><Panel title="Lessons"><DataTable rows={lessons} columns={[{key:"id",label:"Lesson"},{key:"status",label:"Status",render:(v)=><Status value={v}/>},{key:"confidence",label:"Confidence"}]} empty="No lessons"/></Panel><Panel title="Experiments"><DataTable rows={experiments} columns={[{key:"id",label:"Experiment"},{key:"status",label:"Status",render:(v)=><Status value={v}/>},{key:"testing",label:"Origin",render:(v)=><EnvironmentLabel value={v?"MOCK":"REAL"}/>}]} empty="No experiments"/></Panel></div>}</Guarded></>}

export function CreatorJobsPage(){
  const state=useApi("/api/creator-jobs"); const [selected,setSelected]=useState(null);
  return <><PageHeader title="Creator Beta" subtitle="统一 CreatorJob、真实 B 站回执、metrics、reflection 与 evidence。"/><Guarded state={state}>{(jobs)=><div className="approval-layout"><Panel title={`${jobs.length} 个创作者任务`}><DataTable rows={jobs} columns={[{key:"job_id",label:"Job"},{key:"topic",label:"Topic"},{key:"status",label:"Status",render:(v)=><Status value={v}/>},{key:"approval_status",label:"Approval",render:(v)=><Status value={v}/>},{key:"publish_status",label:"Publish",render:(v)=><Status value={v}/>},{key:"testing",label:"Origin",render:(v,row)=><EnvironmentLabel value={v||row.dry_run?"MOCK":"REAL"}/> }]} onRow={setSelected} empty="No Alpha22 CreatorJobs"/></Panel>{selected?<aside className="approval-inspector"><div><h2>{selected.topic}</h2><button aria-label="关闭创作者任务" onClick={()=>setSelected(null)}><X size={18}/></button></div><dl><dt>创作者任务</dt><dd className="hash">{selected.job_id}</dd><dt>修订号</dt><dd>{selected.current_revision}</dd><dt>运行 ID</dt><dd>{selected.run_id||"—"}</dd><dt>质量检查</dt><dd><Status value={selected.qa_report?.passed?"PASS":"BLOCKED"}/></dd><dt>视频</dt><dd className="hash">{selected.video_path||"—"}</dd><dt>封面</dt><dd className="hash">{selected.thumbnail_path||"—"}</dd><dt>发布包</dt><dd className="hash">{selected.package_path||"—"}</dd><dt>B 站内容 ID</dt><dd>{selected.platform_content_id||"—"}</dd><dt>指标快照</dt><dd>{selected.metrics?.length||0}</dd><dt>创作反思</dt><dd>{selected.reflection?"已填写":"未填写"}</dd></dl><Panel title="Research / Claims"><pre className="artifact-text compact">{JSON.stringify({sources:selected.research_sources,claims:selected.claims,uncertainties:selected.uncertainties},null,2)}</pre></Panel><Panel title="Publish metadata"><pre className="artifact-text compact">{JSON.stringify({title:selected.selected_title,description:selected.description,tags:selected.tags,qa:selected.qa_report},null,2)}</pre></Panel></aside>:null}</div>}</Guarded></>;
}

export function ApprovalsPage(){
  const [refresh,setRefresh]=useState(0); const state=useApi("/api/approvals",[refresh]); const [selected,setSelected]=useState(null); const [confirm,setConfirm]=useState(null); const [message,setMessage]=useState(null); const [reason,setReason]=useState("");
  async function submit(decision){try{if(["reject","request-revision"].includes(decision)&&!reason.trim())throw new Error("请填写审核理由");const result=decision==="request-revision"?await apiPost(`/api/creator-jobs/${selected.creator_job_id}/request-revision`,{confirmed:true,actor:"human:control-center",reason}):await apiPost(`/api/approvals/${selected.id}/${decision}`,{confirmed:true,expected_hash:selected.hash,expected_scope:selected.scope,expected_version:selected.version,actor:"human:control-center",reason});setMessage(`${result.status}: ${selected.id}`);setConfirm(null);setSelected(null);setReason("");setRefresh((v)=>v+1);}catch(error){setMessage(error.message);setConfirm(null);}}
  return <><PageHeader title="Pending approvals" subtitle="每次批准都会重新校验范围、哈希、版本和状态。"/><Guarded state={state}>{(rows)=><div className="approval-layout"><Panel title={`${rows.length} 项待审批`}><DataTable rows={rows} columns={[{key:"action",label:"Action",render:(v)=>zh(v)},{key:"subject",label:"Subject"},{key:"scope",label:"Scope"},{key:"hash",label:"Hash",render:(v)=>v?.slice(0,12)+"…"},{key:"requested_at",label:"Requested"},{key:"risk",label:"Risk",render:(v)=><Status value={v}/>},{key:"context",label:"Context",render:(v)=><EnvironmentLabel value={v}/>}]} onRow={(row)=>{setSelected(row);setReason("");}} empty="No pending approvals"/></Panel>{selected?<aside className="approval-inspector"><div><h2>{zh(selected.action)}：{selected.subject}</h2><button aria-label="关闭审批" onClick={()=>setSelected(null)}><X size={18}/></button></div><dl><dt>不可变范围</dt><dd>{selected.scope}</dd><dt>哈希</dt><dd className="hash">{selected.hash}</dd><dt>版本</dt><dd>{selected.version}</dd><dt>风险</dt><dd><Status value={selected.risk}/></dd><dt>环境</dt><dd><EnvironmentLabel value={selected.context}/></dd></dl>{selected.warnings?.length?<div className="warning-box"><AlertTriangle size={17}/>{selected.warnings.join("; ")}</div>:null}<label>审核理由<textarea aria-label="审核理由" value={reason} onChange={(event)=>setReason(event.target.value)} placeholder="拒绝或要求修订时必填"/></label><div className="approval-actions"><ActionButton onClick={()=>setConfirm("approve")}><Check size={16}/>批准</ActionButton>{selected.creator_job_id?<ActionButton secondary onClick={()=>setConfirm("request-revision")}><RotateCcw size={16}/>要求修订</ActionButton>:null}<ActionButton danger onClick={()=>setConfirm("reject")}><X size={16}/>拒绝</ActionButton></div></aside>:null}</div>}</Guarded>{message?<div className="toast">{message}</div>:null}{confirm?<ConfirmDialog title={`确认${confirm === "approve" ? "批准" : confirm === "reject" ? "拒绝" : "要求修订"}`} message="此操作将按 Alpha20 安全策略和不可变审批上下文重新校验。" onCancel={()=>setConfirm(null)} onConfirm={()=>submit(confirm)}/>:null}</>;
}

export function SkillsPage(){const state=useMulti(["/api/capabilities","/api/skills","/api/workflows","/api/workflow-recipes"]);return <><PageHeader title="Skills / Workflows" subtitle="注册能力、批准技能和可复用 recipe。"/><Guarded state={state}>{([caps,skills,workflows,recipes])=><div className="two-column"><Panel title="Capabilities"><DataTable rows={caps} columns={[{key:"capability_id",label:"Capability"},{key:"maturity",label:"Maturity",render:(v)=><Status value={v}/>},{key:"owner",label:"Owner"}]} empty="No capabilities"/></Panel><Panel title="Skills"><DataTable rows={skills} columns={[{key:"skill_id",label:"Skill"},{key:"status",label:"Status",render:(v)=><Status value={v}/>},{key:"version",label:"Version"}]} empty="No registered skills"/></Panel><Panel title="Workflow plans"><DataTable rows={workflows} columns={[{key:"workflow_id",label:"Workflow"},{key:"status",label:"Status",render:(v)=><Status value={v}/>},{key:"recipe_id",label:"Recipe"}]} empty="No workflow plans"/></Panel><Panel title="Recipes"><DataTable rows={recipes} columns={[{key:"recipe_id",label:"Recipe"},{key:"status",label:"Status",render:(v)=><Status value={v}/>},{key:"confidence",label:"Confidence"}]} empty="No recipes"/></Panel></div>}</Guarded></>}

export function AuditPage(){const state=useMulti(["/api/audit","/api/errors"]);return <><PageHeader title="Logs / Audit" subtitle="应用层逻辑审计；secret 已脱敏，不宣称 tamper-proof。"/><Guarded state={state}>{([audit,errors])=><div className="two-column"><Panel title="Audit events"><DataTable rows={audit.slice().reverse()} columns={[{key:"timestamp",label:"Time"},{key:"actor",label:"Actor"},{key:"action",label:"Action"},{key:"decision",label:"Decision",render:(v)=><Status value={v}/>},{key:"result",label:"Result"}]} empty="No audit events"/></Panel><Panel title="Failures"><DataTable rows={errors} columns={[{key:"run_id",label:"Run"},{key:"stage",label:"Stage"},{key:"category",label:"Category"},{key:"status",label:"Status",render:(v)=><Status value={v}/>}]} empty="No failures"/></Panel></div>}</Guarded></>}

export function ConfirmDialog({title,message,onCancel,onConfirm}){return <div className="modal-backdrop" role="presentation"><div className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-title"><ShieldCheck size={28}/><h2 id="confirm-title">{title}</h2><p>{message}</p><div><ActionButton secondary onClick={onCancel}>取消</ActionButton><ActionButton onClick={onConfirm}>确认</ActionButton></div></div></div>}

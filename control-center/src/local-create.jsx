import React, { useEffect, useState } from "react";
import { apiPost } from "./api";
import { useApi } from "./hooks";
import { ActionButton, DataTable, ErrorState, Loading, PageHeader, Panel, Status } from "./components";
import { zhPhase } from "./zh";

const emptyScene = (index) => ({
  scene_id: `scene_${index}`, backend: "h3_staged_i2v", prompt: "", narration: "",
  reference_image: "", workflowText: "", requested_duration_sec: 3,
});

export function LocalCreatePage() {
  const [title, setTitle] = useState("");
  const [scenes, setScenes] = useState([emptyScene(1)]);
  const [refresh, setRefresh] = useState(0);
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const jobs = useApi("/api/local-create/jobs", [refresh]);
  useEffect(() => { const timer = window.setInterval(() => setRefresh((value) => value + 1), 5000); return () => window.clearInterval(timer); }, []);

  function changeScene(index, key, value) {
    setScenes((current) => current.map((scene, position) => position === index ? {...scene, [key]: value} : scene));
  }

  function payload() {
    return {
      title: title.trim(), width: 1280, height: 720, fps: 24,
      scenes: scenes.map((scene) => {
        const base = {scene_id: scene.scene_id.trim(), backend: scene.backend,
          prompt: scene.prompt.trim(), narration: scene.narration.trim(),
          requested_duration_sec: Number(scene.requested_duration_sec)};
        if (scene.backend === "h3_staged_i2v") return {...base, reference_image: scene.reference_image.trim()};
        return {...base, workflow: JSON.parse(scene.workflowText)};
      }),
    };
  }

  async function submit() {
    setBusy(true); setMessage("");
    try {
      const result = await apiPost("/api/local-create/jobs", {confirmed: true, spec: payload()});
      setSelected(result.run_id); setMessage(`已提交 ${result.run_id}。生成在后台运行，可在本页查看状态。`);
      setRefresh((value) => value + 1);
    } catch (error) { setMessage(error.message); }
    finally { setBusy(false); }
  }

  async function resume(runId) {
    setBusy(true); setMessage("");
    try {
      await apiPost(`/api/local-create/jobs/${encodeURIComponent(runId)}/resume`, {confirmed: true});
      setMessage(`${runId} 已请求恢复。`); setRefresh((value) => value + 1);
    } catch (error) { setMessage(error.message); }
    finally { setBusy(false); }
  }

  const current = jobs.data?.find((job) => job.run_id === selected) || jobs.data?.[0];
  const videoUrl = current?.status === "COMPLETE" && /^local_[0-9_]+[a-f0-9]{8}$/.test(current.run_id)
    ? `/api/local-create/jobs/${current.run_id}/video` : null;

  return <>
    <PageHeader title="本地创作" subtitle="自己写提示词、旁白与 ComfyUI API 工作流；串行生成、配音、剪辑，仅供人工审看。"/>
    <div className="two-column">
      <Panel title="创建任务">
        <div className="creator-form">
          <label>标题<input aria-label="标题" value={title} onChange={(event) => setTitle(event.target.value)}/></label>
          {scenes.map((scene, index) => <fieldset key={index}>
            <legend>镜头 {index + 1}</legend>
            <div className="creator-form-row">
              <label>镜头 ID<input aria-label={`镜头 ${index + 1} ID`} value={scene.scene_id} onChange={(event) => changeScene(index, "scene_id", event.target.value)}/></label>
              <label>视频后端<select aria-label={`镜头 ${index + 1} 后端`} value={scene.backend} onChange={(event) => changeScene(index, "backend", event.target.value)}><option value="h3_staged_i2v">MiniMax H3 分阶段单图视频</option><option value="comfyui_api">自定义 ComfyUI API 工作流</option></select></label>
            </div>
            <label>画面/动作提示词<textarea aria-label={`镜头 ${index + 1} 提示词`} value={scene.prompt} onChange={(event) => changeScene(index, "prompt", event.target.value)}/></label>
            <label>配音文案<textarea aria-label={`镜头 ${index + 1} 配音文案`} value={scene.narration} onChange={(event) => changeScene(index, "narration", event.target.value)}/></label>
            {scene.backend === "h3_staged_i2v"
              ? <label>本机参考图片绝对路径<input aria-label={`镜头 ${index + 1} 参考图片`} value={scene.reference_image} onChange={(event) => changeScene(index, "reference_image", event.target.value)} placeholder="D:/Pictures/reference.png"/></label>
              : <><label>预期镜头秒数<input type="number" min="0.1" max="8" step="0.1" value={scene.requested_duration_sec} onChange={(event) => changeScene(index, "requested_duration_sec", event.target.value)}/></label><label>ComfyUI API-format JSON 工作流<textarea className="workflow-json" aria-label={`镜头 ${index + 1} 工作流 JSON`} value={scene.workflowText} onChange={(event) => changeScene(index, "workflowText", event.target.value)} placeholder='{"_alysia":{"api_format":true,"measured_peak_vram_mb":...},"prompt":{...}}'/></label><p className="muted">仅粘贴你信任的 API 节点图，必须含 SaveVideo、参数绑定和实测显存峰值（≤6144 MiB）。旧版 H3 一次性 T2V 工作流不满足此门槛。</p></>}
          </fieldset>)}
          <div className="creator-form-actions"><ActionButton secondary disabled={scenes.length >= 5 || busy} onClick={() => setScenes((value) => [...value, emptyScene(value.length + 1)])}>添加镜头</ActionButton>{scenes.length > 1 && <ActionButton secondary disabled={busy} onClick={() => setScenes((value) => value.slice(0, -1))}>移除末镜头</ActionButton>}<ActionButton disabled={busy} onClick={submit}>{busy ? "提交中…" : "生成视频 + 配音 + 剪辑"}</ActionButton></div>
          {message && <div className="notice" role="status">{message}</div>}
        </div>
      </Panel>
      <div>
        <Panel title="任务进度">{jobs.loading ? <Loading/> : jobs.error ? <ErrorState message={jobs.error}/> : <DataTable rows={jobs.data} columns={[{key:"run_id",label:"任务"},{key:"phase",label:"阶段",render:zhPhase},{key:"status",label:"状态",render:(value)=><Status value={value}/>}]} onRow={(row) => setSelected(row.run_id)} empty="还没有本地创作任务"/>}</Panel>
        {current && <Panel title={`审看 · ${current.run_id}`}><p><Status value={current.status}/> · {zhPhase(current.phase)}</p>{current.error && <p className="warning-box">{current.error}</p>}{videoUrl ? <video className="media-preview" controls src={videoUrl}/> : <p className="muted">成片需生成完成并通过 QA 才能预览。</p>}{current.qa && <p className="muted">视频质量检查：{current.qa.passed ? "通过" : "失败"}</p>}{["FAILED", "RUNNING", "PENDING"].includes(current.status) && <ActionButton secondary disabled={busy} onClick={() => resume(current.run_id)}>恢复任务</ActionButton>}</Panel>}
      </div>
    </div>
  </>;
}

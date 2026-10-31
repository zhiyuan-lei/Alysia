import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { App } from "./App";
import { safeArtifactUrl } from "./api";

const run = { run_id:"run_1", topic:"Alpha21 control test", stage:"rendering", milestone:"video_ready", status:"running", testing:true, review_ready:false };
const approval = { id:"publish:run_1", action:"Publish", subject:"Alpha21 demo", scope:"publish:mock", hash:"a".repeat(64), version:"publish-package-v1", requested_at:"2026-08-09", risk:"high", context:"MOCK", warnings:[] };

function response(payload, status=200) {
  return Promise.resolve({ ok:status>=200&&status<300, status, statusText:String(status), json:async()=>payload, text:async()=>typeof payload==="string"?payload:JSON.stringify(payload) });
}

function installFetch({ blockedApproval=false, emptyRuns=false }={}) {
  global.fetch = vi.fn((input, options={}) => {
    const url = String(input);
    if (url === "/api/health") return response({status:"healthy",csrf_token:"csrf",local_only:true});
    if (url === "/api/dashboard") return response({
      health:{alpha18:{status:"BLOCKED",blocking_findings:["regression"]},alpha19:{open:0},alpha20:{enabled:true}},
      resources:{gpu:{used_mb:1024,total_mb:8188},ram:{used_mb:12000,total_mb:24000},disk:{free_gb:100},guard:{status:"safe"}},
      providers:[{provider_id:"visual.comfyui-h3",health_status:"healthy",health_details:"local H3 ready"}],
      runs:emptyRuns?[]:[run],approvals:[approval],errors:[],
    });
    if (url === "/api/runs") return response(emptyRuns?[]:[run]);
    if (url === "/api/runs/run_1") return response({summary:run,state:{},timeline:[{label:"Topic",status:"completed"},{label:"Render",status:"running"}],qa:[],failures:[]});
    if (url === "/api/runs/run_1/artifacts") return response([]);
    if (url === "/api/approvals") return response([approval]);
    if (url === "/api/local-create/jobs" && options.method === "POST") return response({run_id:"local_20261002_110000_abcdef12",status:"PENDING"});
    if (url === "/api/local-create/jobs") return response([]);
    if (url.includes("/approve") && options.method === "POST") return blockedApproval?response({detail:"approval_artifact_hash_mismatch"},403):response({status:"approved"});
    return response([]);
  });
}

beforeEach(()=>{ window.location.hash="#/dashboard"; installFetch(); });
afterEach(()=>{ cleanup(); vi.restoreAllMocks(); });

describe("Alysia Control Center",()=>{
  it("renders Dashboard, H3 health and Evaluation BLOCKED state",async()=>{
    render(<App/>);
    expect(await screen.findByRole("heading",{name:"总览"})).toBeInTheDocument();
    expect(await screen.findByText("ComfyUI / MiniMax H3")).toBeInTheDocument();
    expect(await screen.findAllByText("正常")).not.toHaveLength(0);
    expect(await screen.findByText("晋级受阻")).toBeInTheDocument();
  });

  it("renders Run detail and real backend timeline",async()=>{
    window.location.hash="#/runs/run_1";
    render(<App/>);
    expect(await screen.findByRole("heading",{name:"任务详情"})).toBeInTheDocument();
    expect(await screen.findByText("阶段时间线")).toBeInTheDocument();
    expect(await screen.findByText("渲染")).toBeInTheDocument();
  });

  it("renders empty state without production fake rows",async()=>{
    installFetch({emptyRuns:true});
    window.location.hash="#/runs";
    render(<App/>);
    expect(await screen.findByText("没有符合条件的任务")).toBeInTheDocument();
  });

  it("renders Pending approval and requires confirmation",async()=>{
    window.location.hash="#/approvals";
    render(<App/>);
    fireEvent.click(await screen.findByText("Alpha21 demo"));
    fireEvent.click(screen.getByRole("button",{name:"批准"}));
    expect(screen.getByRole("dialog")).toHaveTextContent("确认批准");
    expect(screen.getByRole("dialog")).toHaveTextContent("按 Alpha20 安全策略");
  });

  it("shows blocked approval error returned by backend",async()=>{
    installFetch({blockedApproval:true});
    window.location.hash="#/approvals";
    render(<App/>);
    fireEvent.click(await screen.findByText("Alpha21 demo"));
    fireEvent.click(screen.getByRole("button",{name:"批准"}));
    fireEvent.click(screen.getByRole("button",{name:"确认"}));
    await waitFor(()=>expect(screen.getByText("approval_artifact_hash_mismatch")).toBeInTheDocument());
  });

  it("rejects unsafe artifact preview URLs",()=>{
    expect(safeArtifactUrl("/api/runs/run_1/artifacts/final_video")).toBe("/api/runs/run_1/artifacts/final_video");
    expect(safeArtifactUrl("/api/runs/run_1/artifacts/../../secret")).toBeNull();
    expect(safeArtifactUrl("file:///D:/secret.txt")).toBeNull();
    expect(safeArtifactUrl("https://example.com/video.mp4")).toBeNull();
  });

  it("submits user-authored H3 scene from the local creation page",async()=>{
    window.location.hash="#/local-create";
    render(<App/>);
    expect(await screen.findByRole("heading",{name:"本地创作"})).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("标题"),{target:{value:"我的视频"}});
    fireEvent.change(screen.getByLabelText("镜头 1 提示词"),{target:{value:"人物眨眼，花瓣飘落"}});
    fireEvent.change(screen.getByLabelText("镜头 1 配音文案"),{target:{value:"你好。"}});
    fireEvent.change(screen.getByLabelText("镜头 1 参考图片"),{target:{value:"D:/Pictures/reference.png"}});
    fireEvent.click(screen.getByRole("button",{name:"生成视频 + 配音 + 剪辑"}));
    await waitFor(()=>expect(global.fetch).toHaveBeenCalledWith("/api/local-create/jobs",expect.objectContaining({method:"POST"})));
    const call=global.fetch.mock.calls.find(([url,options])=>url==="/api/local-create/jobs"&&options.method==="POST");
    expect(JSON.parse(call[1].body).spec.scenes[0]).toMatchObject({
      backend:"h3_staged_i2v",prompt:"人物眨眼，花瓣飘落",narration:"你好。",reference_image:"D:/Pictures/reference.png",
    });
  });
});

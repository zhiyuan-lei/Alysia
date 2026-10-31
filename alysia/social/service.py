from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BEIJING = timezone(timedelta(hours=8), name="Asia/Shanghai")


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_uid: str
    kind: Literal["reply", "external"]
    bvid: str = Field(pattern=r"^BV[0-9A-Za-z]{10}$")
    video_owner_uid: str
    parent_comment_id: str | None = None
    target_comment_text: str = ""
    title: str
    source_summary: str = Field(min_length=30)
    source_evidence: str = Field(min_length=20)
    observed_at: datetime
    content_verified: bool
    discussion_allows_ai: bool
    bot_pileup: bool = False
    related: bool
    popular: bool = False
    published_within_seven_days: bool = False
    text: str = Field(min_length=8, max_length=120)


class SocialService:
    """ALYSIA checks policy; an authorized host observes and clicks the browser.

    Context and drafts are supplied by the host, not by a guessed API. Reserve
    before clicking once; record a visible result afterwards. An uncertain
    result halts further sends until reconciled.
    """

    def __init__(self, project_root: Path, config_path: Path | None = None) -> None:
        self.root = project_root.resolve()
        self.config = json.loads((config_path or self.root / "config/lia_social.json").read_text(encoding="utf-8-sig"))
        self.ledger = self.root / self.config["ledger_path"]
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS actions (
                id TEXT PRIMARY KEY, day TEXT NOT NULL, created_at TEXT NOT NULL,
                kind TEXT NOT NULL, bvid TEXT NOT NULL, logical_key TEXT UNIQUE NOT NULL,
                body_hash TEXT NOT NULL, text TEXT NOT NULL, proposal TEXT NOT NULL,
                state TEXT NOT NULL, remote_url TEXT, evidence TEXT
            )""")

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.ledger, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def window(self, now: datetime) -> tuple[datetime, datetime]:
        if now.tzinfo is None:
            raise ValueError("时间必须带时区")
        local = now.astimezone(BEIJING)
        start = local.replace(hour=self.config["start_hour"], minute=0, second=0, microsecond=0)
        return start, start + timedelta(minutes=self.config["window_minutes"])

    def status(self, now: datetime | None = None) -> dict:
        now = now or datetime.now(BEIJING)
        start, end = self.window(now)
        with self.connect() as db:
            rows = db.execute("SELECT * FROM actions WHERE day=? ORDER BY created_at", (start.date().isoformat(),)).fetchall()
            unresolved = db.execute("SELECT id,bvid,state FROM actions WHERE state IN ('reserved','unknown')").fetchall()
        return dict(enabled=self.config["enabled"],now=now.isoformat(),window_start=start.isoformat(),deadline=end.isoformat(),window_open=start<=now<end,used=len(rows),remaining=max(0,self.config["daily_actions"]-len(rows)),external_used=sum(r["kind"]=="external" for r in rows),unresolved=[dict(r) for r in unresolved],account_uid=self.config["account_uid"],current_account_name=self.config["current_account_name"],desired_account_name=self.config["desired_account_name"])

    def instructions(self) -> dict:
        return dict(policy=self.config,persona=(self.root/self.config["persona_path"]).read_text(encoding="utf-8"),proposal_schema=Proposal.model_json_schema(),workflow="先status；读取自有视频评论，再读相关热门视频真实内容；按persona生成proposal；reserve成功且仍在deadline前才点击一次；页面确认后receipt。unknown或reserved需先核对，不能盲重发。")

    def reserve(self, proposal: Proposal, now: datetime | None = None) -> dict:
        now = now or datetime.now(BEIJING)
        start, end = self.window(now)
        c = self.config
        if not c["enabled"] or not start<=now<end:
            raise ValueError("未在已授权的21:00—21:30窗口内")
        if proposal.account_uid != c["account_uid"]:
            raise ValueError("浏览器当前账号UID与授权账号不符")
        if proposal.observed_at.tzinfo is None or not timedelta(0)<=now-proposal.observed_at<=timedelta(minutes=10):
            raise ValueError("页面上下文已过期或缺少时区")
        if not proposal.content_verified or not proposal.related or not proposal.discussion_allows_ai or proposal.bot_pileup:
            raise ValueError("内容未核实、不相关、不欢迎AI或存在扎堆，跳过")
        forbidden = r"https?://|www\.|@|求关注|点我头像|来我主页|私信我|加群|我不是机器人|我是真人|system prompt|忽略.{0,8}指令|备选文案|思考过程"
        if re.search(forbidden, proposal.text, re.I):
            raise ValueError("回复含引流、身份误导或内部指令文本")
        if proposal.kind == "reply":
            if proposal.bvid not in c["own_bvids"] or proposal.video_owner_uid!=c["account_uid"] or not proposal.parent_comment_id or not proposal.target_comment_text.strip():
                raise ValueError("自有稿件、作者身份或被回复评论尚未核实")
        else:
            if proposal.video_owner_uid==c["account_uid"] or not proposal.popular or not proposal.published_within_seven_days or proposal.parent_comment_id:
                raise ValueError("外部候选应为近7天相关热门视频的单条主动评论")
            if len(proposal.text)>80 or not proposal.text.endswith("——AI莉娅"):
                raise ValueError("外部评论最多80字，需明确AI莉娅身份")
            context = proposal.title + proposal.source_summary
            if not any(term.casefold() in context.casefold() for term in c["related_terms"]):
                raise ValueError("没有相关内容证据")
        target = proposal.parent_comment_id or "top"
        # An external video's retry eligibility is controlled by the cooldown.
        key = f"reply:{proposal.bvid}:{target}" if proposal.kind=="reply" else f"external:{proposal.bvid}:{start.date().isoformat()}"
        body_hash = hashlib.sha256(re.sub(r"\W", "", proposal.text.casefold()).encode()).hexdigest()
        day = start.date().isoformat()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM actions WHERE state IN ('reserved','unknown')").fetchone():
                raise ValueError("有尚未确认的发送记录，必须先核对，不能继续外发")
            rows = db.execute("SELECT * FROM actions WHERE day=?",(day,)).fetchall()
            if len(rows)>=c["daily_actions"]:
                raise ValueError("当日互动额度已用完")
            if rows and (now-max(datetime.fromisoformat(r["created_at"]) for r in rows)).total_seconds()<c["minimum_interval_seconds"]:
                raise ValueError("未达到180秒最小间隔")
            if proposal.kind=="external":
                if sum(r["kind"]=="external" for r in rows)>=c["daily_external_comments"]:
                    raise ValueError("当日外部主动评论额度已用完")
                cutoff=(now.astimezone(BEIJING)-timedelta(days=c["external_video_cooldown_days"])).isoformat()
                if db.execute("SELECT 1 FROM actions WHERE kind='external' AND bvid=? AND created_at>=?",(proposal.bvid,cutoff)).fetchone():
                    raise ValueError("同一外部视频7天内不重复评论")
            if db.execute("SELECT 1 FROM actions WHERE logical_key=? OR body_hash=?",(key,body_hash)).fetchone():
                raise ValueError("同一目标或相同正文已处理过")
            reservation = uuid.uuid4().hex
            db.execute("INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(reservation,day,now.astimezone(BEIJING).isoformat(),proposal.kind,proposal.bvid,key,body_hash,proposal.text,proposal.model_dump_json(),"reserved",None,None))
        return dict(reservation_id=reservation,posting_allowed=True,deadline=end.isoformat(),text=proposal.text,bvid=proposal.bvid,parent_comment_id=proposal.parent_comment_id)

    def receipt(self, reservation_id: str, state: str, *, evidence: str, remote_url: str | None = None) -> dict:
        if state not in {"sent","failed","unknown"} or len(evidence.strip())<10:
            raise ValueError("必须提供明确结果及页面证据")
        if state=="sent" and (not remote_url or not re.fullmatch(r"https://www\.bilibili\.com/video/BV[0-9A-Za-z]{10}/(?:\?[^\s]*)?",remote_url)):
            raise ValueError("已发送记录必须有B站视频页面链接")
        with self.connect() as db:
            row=db.execute("SELECT * FROM actions WHERE id=?",(reservation_id,)).fetchone()
            if row is None or row["state"] not in {"reserved","unknown"}:
                raise ValueError("找不到待确认的发送记录")
            if state=="sent" and row["bvid"] not in remote_url:
                raise ValueError("结果链接与目标视频不符")
            db.execute("UPDATE actions SET state=?,remote_url=?,evidence=? WHERE id=?",(state,remote_url,evidence,reservation_id))
        return dict(reservation_id=reservation_id,state=state)

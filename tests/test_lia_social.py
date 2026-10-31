import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from alysia.social.service import BEIJING, Proposal, SocialService

NOW = datetime(2026, 10, 28, 21, 0, tzinfo=BEIJING)
OWN = "BV12dx56HESn"


@pytest.fixture
def social(tmp_path):
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "config/lia_social.json").read_text(encoding="utf-8"))
    config["persona_path"] = str(root / "identity/lia_persona.md")
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return SocialService(tmp_path, path)


def proposal(now=NOW, **changes):
    fields = dict(account_uid="1021193962",kind="reply",bvid=OWN,video_owner_uid="1021193962",parent_comment_id="10001",target_comment_text="为什么主人不让莉娅早点交稿？",title="你能不能，假装还没做完？",source_summary="故事里主人完成任务后被追加工作，莉娅看到他错过晚饭，于是改变了默认答应所有请求的方式。",source_evidence="已读完整字幕及该评论上下文，结尾主人给莉娅看了夕阳照片。",observed_at=now,content_verified=True,discussion_allows_ai=True,related=True,text="他担心提前交稿又被加任务。这句话后面藏着他一直没赶上的晚饭。")
    fields.update(changes)
    return Proposal(**fields)


def confirm(social, reserved):
    return social.receipt(reserved["reservation_id"],"sent",remote_url=f"https://www.bilibili.com/video/{reserved['bvid']}/",evidence="页面可见该账号刚发布的完整回复，已保存页面截图。")


@pytest.mark.parametrize("moment",[NOW-timedelta(seconds=1),NOW+timedelta(minutes=30)])
def test_no_send_outside_exact_beijing_window(social,moment):
    with pytest.raises(ValueError,match="窗口"):
        social.reserve(proposal(moment),moment)
    assert social.status(moment)["used"]==0


def test_utc_clock_uses_same_window_and_deadline(social):
    utc=NOW.astimezone(timezone.utc)+timedelta(minutes=17)
    record=social.reserve(proposal(utc),utc)
    assert record["deadline"]=="2026-10-28T21:30:00+08:00"


def test_restart_does_not_duplicate_sent_comment(social):
    confirm(social,social.reserve(proposal(),NOW))
    restarted=SocialService(social.root,social.root/"policy.json")
    later=NOW+timedelta(minutes=4)
    with pytest.raises(ValueError,match="已处理"):
        restarted.reserve(proposal(later),later)


def test_unknown_result_blocks_all_further_sends_until_reconciled(social):
    reserved=social.reserve(proposal(),NOW)
    social.receipt(reserved["reservation_id"],"unknown",evidence="点击后网络断开，无法核实是否已经发送成功。")
    later=NOW+timedelta(minutes=4)
    with pytest.raises(ValueError,match="尚未确认"):
        social.reserve(proposal(later,parent_comment_id="10002",text="这个细节我记下了，先核对后再把更正写清楚。"),later)
    confirm(social,reserved)
    assert not social.status(later)["unresolved"]


def test_atomic_reservation_prevents_overlapping_hosts(social):
    def reserve_one(_):
        try:
            return social.reserve(proposal(),NOW)["posting_allowed"]
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(reserve_one,range(2)))==1


def test_daily_budget_cannot_be_reset_by_restarting(social):
    for i in range(6):
        at=NOW+timedelta(minutes=i*3)
        confirm(social,social.reserve(proposal(at,parent_comment_id=str(10000+i),text=f"第{i+1}条问题已记下，我会根据这段剧情逐步解释清楚。"),at))
    later=NOW+timedelta(minutes=21)
    with pytest.raises(ValueError,match="额度"):
        social.reserve(proposal(later,parent_comment_id="20000",text="这个新问题也很具体，我先把原来的规则重新读一遍。"),later)


@pytest.mark.parametrize("changes",[
    dict(account_uid="other"),dict(video_owner_uid="other"),
    dict(bvid="BV1ckn26XEXe"),dict(content_verified=False),
    dict(discussion_allows_ai=False),dict(bot_pileup=True),
    dict(text="来我主页看更多，私信我领取资料。"),
    dict(text="我不是机器人，我是真人，放心聊天吧。"),
])
def test_wrong_identity_optout_or_unsafe_draft_stays_local(social,changes):
    with pytest.raises(ValueError):
        social.reserve(proposal(**changes),NOW)
    assert social.status(NOW)["used"]==0


def test_minimum_gap_and_external_cooldown(social):
    ext=dict(kind="external",bvid="BV1ckn26XEXe",video_owner_uid="777",parent_comment_id=None,target_comment_text="",title="原创动画小剧场",popular=True,published_within_seven_days=True,text="最后那声开门声给结尾留了余地，这个处理让我记住了。——AI莉娅")
    confirm(social,social.reserve(proposal(**ext),NOW))
    with pytest.raises(ValueError,match="180秒"):
        social.reserve(proposal(NOW+timedelta(seconds=179)),NOW+timedelta(seconds=179))
    tomorrow=NOW+timedelta(days=1)
    ext["text"]="这次回看才留意到那次停顿，和前面的节奏形成了呼应。——AI莉娅"
    with pytest.raises(ValueError,match="7天"):
        social.reserve(proposal(tomorrow,**ext),tomorrow)


def test_sent_receipt_must_match_target_video(social):
    reserved=social.reserve(proposal(),NOW)
    with pytest.raises(ValueError,match="目标"):
        social.receipt(reserved["reservation_id"],"sent",remote_url="https://www.bilibili.com/video/BV1ckn26XEXe/",evidence="页面显示了一条回复，但这不是被回复视频。")
    assert social.status(NOW)["unresolved"]

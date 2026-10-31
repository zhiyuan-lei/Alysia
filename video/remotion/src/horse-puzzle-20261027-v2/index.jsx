import React from 'react';
import {AbsoluteFill, Audio, Composition, Img, Sequence, getInputProps, interpolate, registerRoot, spring, staticFile, useCurrentFrame} from 'remotion';

const P = {paper: '#F6F2E9', ink: '#203442', muted: '#7B8587', line: '#DCDDD5', red: '#DE6D55', blue: '#4D8AB4', gold: '#D3A342', green: '#6D9E88', purple: '#9C87B1'};
const COLORS = {A: P.red, B: P.blue, C: P.gold, D: P.green, E: P.purple};
const GROUPS = ['A', 'B', 'C', 'D', 'E'];
const CANDIDATES = ['A2', 'A3', 'B1', 'B2', 'C1'];
const clamp = (n) => Math.min(1, Math.max(0, n));
const ease = (n) => 1 - (1 - clamp(n)) ** 3;

const Horse = ({color = P.red, width = 100, run = false}) => {
  const frame = useCurrentFrame();
  const bob = run ? Math.sin(frame * .55) * width * .025 : 0;
  return <div style={{width, height: width * .72, flexShrink: 0, position: 'relative', transform: `translateY(${bob}px) rotate(${run ? Math.sin(frame * .45) * 1.8 : 0}deg)`}}>
    <Img alt="Q版小马" src={staticFile('assets/pony.png')} style={{width: '100%', height: '100%', objectFit: 'contain', filter: color === '#A8AEA9' ? 'grayscale(1)' : 'none'}}/>
    <div style={{position: 'absolute', left: width * .05, bottom: width * .03, width: Math.max(7, width * .075), height: Math.max(7, width * .075), borderRadius: '50%', background: color, border: '2px solid #FFFDF8'}}/>
  </div>;
};

const Card = ({id, dead = false, active = false, width = 180, tall = false, delay = 0}) => {
  const frame = useCurrentFrame();
  const appear = ease((frame - delay) / 16);
  return <div style={{width, height: tall ? 220 : 76, boxSizing: 'border-box', border: `2px solid ${dead ? P.line : active ? COLORS[id[0]] : '#DFE0D8'}`, borderRadius: 18, background: dead ? '#E8E8E1' : '#FFFDF8', display: 'flex', flexDirection: tall ? 'column' : 'row', alignItems: 'center', justifyContent: 'center', gap: tall ? 8 : 4, position: 'relative', opacity: appear * (dead ? .34 : 1), transform: `translateY(${(1 - appear) * 20}px)`, boxShadow: active ? `0 5px 0 ${COLORS[id[0]]}28` : 'none'}}>
    <Horse color={dead ? '#A8AEA9' : COLORS[id[0]]} width={tall ? 172 : width > 170 ? 104 : 76}/>
    <span style={{fontSize: tall ? 52 : 34, fontWeight: 850, color: dead ? '#8C9692' : COLORS[id[0]], lineHeight: 1}}>{id}</span>
    {dead ? <svg width="100%" height="100%" style={{position: 'absolute', inset: 0}} viewBox="0 0 180 76" preserveAspectRatio="none"><path d="M12 64L168 12" stroke="#687672" strokeWidth="3.5"/></svg> : null}
  </div>;
};

const Tag = ({children, color = P.ink}) => <div style={{display: 'inline-flex', alignItems: 'center', padding: '13px 26px', borderRadius: 50, color, background: `${color}12`, fontSize: 29, fontWeight: 700}}>{children}</div>;

const Crown = () => <svg width="100" height="70" viewBox="0 0 100 70"><path d="M10 19L30 34L50 6L70 34L90 19L79 62H21Z" fill={P.gold} stroke={P.ink} strokeWidth="3" strokeLinejoin="round"/><path d="M25 53H75" stroke="#FFF8D5" strokeWidth="4"/></svg>;

const removed = (g, r, stage) => (stage >= 1 && 'DE'.includes(g)) || (stage >= 2 && g === 'C' && r >= 2) || (stage >= 3 && g === 'B' && r >= 3) || (stage >= 4 && g === 'A' && r >= 4);

const Matrix = ({stage = 0, compact = false}) => <div style={{display: 'flex', flexDirection: 'column', gap: 13}}>
  <div style={{display: 'flex', marginLeft: 62, gap: 13}}>{[1, 2, 3, 4, 5].map(r => <div key={r} style={{width: compact ? 147 : 219, textAlign: 'center', color: P.muted, fontSize: 25}}>第 {r} 名</div>)}</div>
  {GROUPS.map(g => <div key={g} style={{display: 'flex', alignItems: 'center', gap: 13}}>
    <div style={{width: 49, fontSize: 35, fontWeight: 800, color: COLORS[g]}}>{g}</div>
    {[1, 2, 3, 4, 5].map(r => <Card key={r} id={`${g}${r}`} width={compact ? 147 : 219} dead={removed(g, r, stage)} active={stage > 0 && !removed(g, r, stage)} delay={(r - 1) * 3 + GROUPS.indexOf(g) * 2}/>)}
  </div>)}
</div>;

const Race = ({ids, order, start = 30, final = false}) => {
  const frame = useCurrentFrame();
  const allDone = frame > start + 168;
  return <div>
    <div style={{position: 'relative', height: 390, background: '#FFFDF7', border: `2px solid ${P.line}`, borderRadius: 24, overflow: 'hidden'}}>
      <div style={{position: 'absolute', left: 1090, top: 0, bottom: 0, width: 8, background: `repeating-linear-gradient(0deg, ${P.ink} 0px, ${P.ink} 12px, #FFFFFF 12px, #FFFFFF 24px)`}}/>
      {ids.map((id, i) => {
        const rank = order.indexOf(id);
        const progress = clamp((frame - start) / (112 + rank * 13));
        const x = 100 + 910 * progress;
        return <div key={id} style={{height: 78, position: 'relative', borderBottom: i < 4 ? `1px dashed ${P.line}` : 'none', background: i % 2 === 0 ? '#EFEDE32E' : 'transparent'}}>
          <span style={{position: 'absolute', left: 24, top: 22, fontSize: 29, fontWeight: 800, color: COLORS[id[0]]}}>{id}</span>
          <div style={{position: 'absolute', left: x, top: -3 + (progress < 1 && progress > 0 ? Math.sin(frame * .65 + i) * 2 : 0)}}><Horse color={COLORS[id[0]]} width={110} run={progress > 0 && progress < 1}/></div>
          {progress >= 1 ? <span style={{position: 'absolute', right: 25, top: 20, fontSize: 31, fontWeight: 800, color: final && rank < 2 ? P.red : P.ink}}>{rank + 1}</span> : null}
        </div>;
      })}
    </div>
    <div style={{marginTop: 30, display: 'flex', justifyContent: 'center', gap: 15, alignItems: 'center', minHeight: 55}}>
      {allDone ? final ? <Tag color={P.red}>本场前二 A2、B1 → 全场亚军、季军（示例）</Tag> : order.map((id, i) => <React.Fragment key={id}><span style={{fontSize: 35, fontWeight: 850, color: COLORS[id[0]]}}>{id}</span>{i < 4 ? <span style={{fontSize: 32, color: P.muted}}> &gt; </span> : null}</React.Fragment>) : <Tag>只看先后，不计用时</Tag>}
    </div>
  </div>;
};

const Chain = ({ids}) => <div style={{width: 260, background: '#FFFFFF80', border: `2px solid ${P.line}`, borderRadius: 24, padding: '23px 25px', display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
  <div style={{fontSize: 27, fontWeight: 750, marginBottom: 18}}>三匹确定更快</div>
  {ids.map((id, i) => <React.Fragment key={id}><Card id={id} width={215} dead={i === 3}/>{i < 3 ? <div style={{fontSize: 22, lineHeight: '27px', color: P.muted}}>↓ 更快于</div> : null}</React.Fragment>)}
</div>;

const Opening = () => <div style={{display: 'flex', gap: 65, alignItems: 'center', height: 485}}>
  <div style={{width: 470}}><div style={{fontSize: 152, fontWeight: 900, letterSpacing: -7, lineHeight: 1.1}}><span style={{color: P.red}}>25</span><span style={{fontSize: 85, padding: '0 20px', color: P.muted}}>→</span><span style={{color: P.blue}}>3</span></div><div style={{fontSize: 43, fontWeight: 800, margin: '22px 0 28px'}}>谁是真正的前三名？</div><Tag color={P.red}>只有 7 次比赛机会</Tag><div style={{fontSize: 27, color: P.muted, marginTop: 24}}>没有秒表 · 五条跑道</div></div>
  <div style={{display: 'grid', gridTemplateColumns: 'repeat(5, 126px)', gap: '12px 9px'}}>{Array.from({length: 25}, (_, i) => <div key={i} style={{background: '#FFFDF8', borderRadius: 14, padding: 6}}><Horse color={COLORS[GROUPS[Math.floor(i / 5)]]} width={113}/></div>)}</div>
</div>;

const SceneArt = ({scene, frame}) => {
  const phase = scene.cues.filter(c => c.start_frame <= frame).length;
  if (scene.kind === 'opening') return <Opening/>;
  if (scene.kind === 'mistake') return <div style={{textAlign: 'center', paddingTop: 60}}><div style={{display: 'flex', gap: 18, justifyContent: 'center'}}>{GROUPS.map((g, i) => <div key={g} style={{position: 'relative'}}><Card id={`${g}1`} tall width={220} delay={i * 8}/>{i < 3 ? <div style={{position: 'absolute', top: -29, left: 17, borderRadius: 30, background: P.gold, color: 'white', fontSize: 26, padding: '6px 18px'}}>直接选？</div> : null}</div>)}</div><div style={{marginTop: 48, fontSize: 47, fontWeight: 800, color: phase >= 2 ? P.red : P.ink}}>{phase >= 2 ? '等等：组内第二，仍可能是全场第二！' : '五个小组第一，再取前三？'}</div></div>;
  if (scene.kind === 'unknown') return <div style={{textAlign: 'center', paddingTop: 25}}><Tag>A1 &gt; A2，只说明它们的组内关系</Tag><div style={{display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 70, marginTop: 35}}><div><Card id="A2" tall width={300}/><div style={{fontSize: 30, marginTop: 18}}>红组第二</div></div><div style={{fontSize: 125, fontWeight: 900, color: P.gold}}>?</div><div><Card id="B1" tall width={300}/><div style={{fontSize: 30, marginTop: 18}}>蓝组第一</div></div></div><div style={{fontSize: 36, marginTop: 25, color: P.muted}}>跨组的先后，仍然未知</div></div>;
  if (scene.kind === 'rules') return <div style={{display: 'flex', gap: 25, paddingTop: 55}}>{[['01', '速度固定', '每匹马始终一样快', '没有并列'], ['02', '每场五匹', '五条跑道', '可以重复参赛'], ['03', '只知道名次', '没有秒表', '不能比较各场用时']].map(([n, title, a, b], i) => <div key={n} style={{width: 380, padding: '32px 24px', borderRadius: 24, background: '#FFFDF8', border: `2px solid ${P.line}`, opacity: phase >= Math.min(i + 1, 2) ? 1 : .45}}><div style={{fontSize: 55, fontWeight: 900, color: [P.red, P.blue, P.gold][i]}}>{n}</div><div style={{fontSize: 46, fontWeight: 800, marginTop: 26}}>{title}</div><div style={{fontSize: 30, lineHeight: 1.8, color: P.muted, marginTop: 22}}>{a}<br/>{b}</div></div>)}</div>;
  if (scene.kind === 'groups' || scene.kind === 'ranking') return <Matrix/>;
  if (scene.kind === 'champions') return <Race ids={GROUPS.map(g => `${g}1`)} order={GROUPS.map(g => `${g}1`)} start={scene.cues[1].start_frame + 10}/>;
  if (scene.kind === 'winner') return <div style={{display: 'flex', gap: 75, alignItems: 'center', paddingTop: 35}}><div style={{textAlign: 'center', width: 390}}><Crown/><Card id="A1" tall width={390}/><div style={{fontSize: 42, fontWeight: 850, color: P.gold, marginTop: 20}}>全场冠军</div></div><div style={{fontSize: 36, lineHeight: 1.9}}><div style={{color: P.red, fontSize: 43, fontWeight: 800}}>A1 &gt; B1 &gt; C1 &gt; D1 &gt; E1</div><div>每一组的第一，都比组内其余马快</div><div style={{margin: '25px 0', width: 650, height: 2, background: P.line}}/><Tag color={P.blue}>所以，没有任何马能排在 A1 前面</Tag></div></div>;
  if (scene.kind === 'principle') return <div style={{textAlign: 'center', paddingTop: 55}}><div style={{display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 20}}>{['A1', 'B1', 'C1', 'D1'].map((id, i) => <React.Fragment key={id}><Card id={id} tall width={245} dead={i === 3}/>{i < 3 ? <span style={{fontSize: 53, color: P.muted}}>&gt;</span> : null}</React.Fragment>)}</div><div style={{fontSize: 41, fontWeight: 800, marginTop: 45}}>已有 <span style={{color: P.red}}>3 匹</span> 确定更快 → 最好也只能排第 4</div><div style={{fontSize: 30, color: P.muted, marginTop: 15}}>这一条，足够划掉绝大多数候选</div></div>;
  if (scene.kind === 'eliminate') {
    const chains = {1: ['A1', 'B1', 'C1', 'D1'], 2: ['A1', 'B1', 'C1', 'C2'], 3: ['A1', 'B1', 'B2', 'B3'], 4: ['A1', 'A2', 'A3', 'A4']};
    return <div style={{display: 'flex', gap: 45, alignItems: 'flex-start'}}><Matrix stage={frame > 40 ? scene.stage : scene.stage - 1} compact/><Chain ids={chains[scene.stage]}/></div>;
  }
  if (scene.kind === 'candidates') return <div style={{textAlign: 'center', paddingTop: 52}}><div style={{display: 'flex', gap: 19, justifyContent: 'center'}}>{CANDIDATES.map((id, i) => <Card key={id} id={id} tall width={220} active delay={i * 9}/>)}</div><div style={{marginTop: 45, fontSize: 41, fontWeight: 800}}>争夺两个名额：全场第 <span style={{color: P.red}}>2</span>、第 <span style={{color: P.blue}}>3</span> 名</div><div style={{marginTop: 24}}><Tag color={P.gold}>A1 已经夺冠，不用再跑</Tag></div></div>;
  if (scene.kind === 'final') return phase >= 3 ? <div style={{textAlign: 'center'}}><div style={{display: 'flex', justifyContent: 'center', alignItems: 'flex-end', gap: 30, height: 380}}>{[['A2', '亚军', 92, '#B6C4C8'], ['A1', '冠军', 142, P.gold], ['B1', '季军', 62, '#BE8C6B']].map(([id, label, height, color]) => <div key={id} style={{width: 265}}>{id === 'A1' ? <Crown/> : null}<Card id={id} tall width={265}/><div style={{height, background: color, borderRadius: '0 0 18px 18px', paddingTop: 17, fontSize: 35, fontWeight: 850, color: '#FFFFFF'}}>{label}</div></div>)}</div><div style={{marginTop: 34, fontSize: 38, fontWeight: 800}}>本例全场前三：A1 → A2 → B1</div><div style={{marginTop: 20}}><Tag>第七场取前二，加上早已确定的冠军 A1</Tag></div></div> : <Race ids={CANDIDATES} order={['A2', 'B1', 'C1', 'A3', 'B2']} start={20} final/>;
  return <div style={{textAlign: 'center', paddingTop: 20}}><div style={{display: 'flex', gap: 23, alignItems: 'center', justifyContent: 'center'}}>{[['5', '分组'], ['1', '冠军赛'], ['1', '候选赛'], ['7', '总场数']].map(([n, name], i) => <React.Fragment key={name}>{i ? <span style={{fontSize: 65, color: P.muted}}>{i === 3 ? '=' : '+'}</span> : null}<div style={{width: 200, padding: '20px 10px', border: `2px solid ${P.line}`, borderRadius: 24, background: i === 3 ? P.ink : '#FFFDF8', color: i === 3 ? 'white' : P.ink}}><div style={{fontSize: 128, lineHeight: 1.2, fontWeight: 900, color: i === 3 ? '#E7C26B' : P.ink}}>{n}</div><div style={{fontSize: 29, marginTop: 12}}>{name}</div></div></React.Fragment>)}</div><div style={{marginTop: 48, fontSize: 41, fontWeight: 850, color: P.red}}>已有三匹确定更快，就能划掉</div><div style={{marginTop: 18, fontSize: 30, color: P.muted}}>让每一次比赛，都带来新的信息。</div></div>;
};

const Presenter = ({scene, frame, entry}) => {
  const at = (i) => scene.cues[Math.min(i, scene.cues.length - 1)].start_frame;
  const plans = {
    opening: [{from: 0, pose: 'wave', motion: 'wave'}, {from: at(1), pose: 'point', motion: 'point'}],
    mistake: [{from: 0, pose: 'think', motion: 'think'}, {from: at(1), pose: 'surprise', motion: 'recoil'}],
    unknown: [{from: 0, pose: 'think', motion: 'think'}, {from: at(2), pose: 'point', motion: 'point'}],
    rules: [{from: 0, pose: 'explain', motion: 'explain'}, {from: at(1), pose: 'point', motion: 'point'}],
    champions: [{from: 0, pose: 'point', motion: 'point'}, {from: at(1), pose: 'explain', motion: 'explain'}, {from: at(2), pose: 'reveal', motion: 'reveal'}],
    winner: [{from: 0, pose: 'reveal', motion: 'reveal'}, {from: at(2), pose: 'celebrate', motion: 'celebrate'}],
    principle: [{from: 0, pose: 'think', motion: 'think'}, {from: at(2), pose: 'explain', motion: 'explain'}],
    candidates: [{from: 0, pose: 'point', motion: 'point'}, {from: at(1), pose: 'explain', motion: 'explain'}, {from: at(2), pose: 'reveal', motion: 'reveal'}],
    final: [{from: 0, pose: 'point', motion: 'point'}, {from: at(2), pose: 'celebrate', motion: 'celebrate'}],
    ending: [{from: 0, pose: 'reveal', motion: 'reveal'}, {from: at(1), pose: 'think', motion: 'think'}, {from: at(2), pose: 'wave', motion: 'wave'}],
  };
  const actions = plans[scene.kind] || [{from: 0, pose: 'point', motion: 'point'}, ...scene.cues.slice(1).map((cue, i) => ({from: cue.start_frame, pose: i % 2 ? 'point' : 'explain', motion: i % 2 ? 'point' : 'explain'}))];
  const index = Math.max(0, actions.findLastIndex(action => action.from <= frame));
  const action = actions[index];
  const previous = actions[Math.max(0, index - 1)];
  const age = frame - action.from;
  const fade = interpolate(age, [0, 7], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  let x = (1 - entry) * 35;
  let y = Math.sin(frame / 19) * 2;
  let angle = Math.sin(frame / 45) * .5;
  if (action.motion === 'think') angle = -2.7 + Math.sin(age / 24) * .5;
  if (action.motion === 'point') angle = -1.5 * ease(age / 16);
  if (action.motion === 'wave') {angle += Math.sin(age / 8) * 2.2 * Math.exp(-age / 130); x += Math.sin(age / 8) * 3;}
  if (action.motion === 'recoil') {const reaction = Math.sin(Math.PI * clamp(age / 40)); x += reaction * 16; angle += reaction * 5;}
  if (action.motion === 'celebrate') {y -= Math.abs(Math.sin(age * Math.PI / 16)) * 20 * Math.exp(-age / 52); angle += Math.sin(age / 9) * 1.8 * Math.exp(-age / 60);}
  if (action.motion === 'reveal') angle += Math.sin(age / 25) * 1.1;
  const imageStyle = {position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain'};
  return <div style={{position: 'absolute', left: 1460, top: 331, width: 370, height: 555, opacity: entry, transformOrigin: '50% 94%', transform: `translate(${x}px, ${y + (1 - entry) * 20}px) rotate(${angle}deg)`}}>
    {index > 0 && fade < 1 ? <Img src={staticFile(`assets/presenter_${previous.pose}.png`)} style={{...imageStyle, opacity: 1 - fade}}/> : null}
    <Img src={staticFile(`assets/presenter_${action.pose}.png`)} style={{...imageStyle, opacity: index > 0 ? fade : 1}}/>
    {action.motion === 'recoil' && age < 42 ? <div style={{position: 'absolute', left: 10, top: 36 - ease(age / 20) * 15, fontSize: 72, fontWeight: 900, color: P.red, opacity: clamp((42 - age) / 14), transform: `rotate(-12deg) scale(${.7 + ease(age / 10) * .3})`}}>!</div> : null}
    {action.motion === 'celebrate' && age < 65 ? [0, 1, 2].map(i => <svg key={i} width="28" height="28" viewBox="0 0 40 40" style={{position: 'absolute', left: 25 + i * 135, top: 90 + (i % 2) * 45 - age * .6, opacity: clamp((65 - age) / 28), transform: `rotate(${age * 2 + i * 20}deg)`}}><path d="M20 1L25 15L39 20L25 25L20 39L15 25L1 20L15 15Z" fill={P.gold}/></svg>) : null}
  </div>;
};

const Scene = ({scene}) => {
  const frame = useCurrentFrame();
  const entry = spring({frame, fps: 30, config: {damping: 25, stiffness: 130}});
  const cue = scene.cues.find(c => c.start_frame <= frame && frame < c.end_frame);
  return <AbsoluteFill style={{backgroundColor: P.paper, color: P.ink, fontFamily: 'Microsoft YaHei, sans-serif', backgroundImage: 'radial-gradient(#2034420C 1px, transparent 1px)', backgroundSize: '24px 24px'}}>
    <div style={{position: 'absolute', top: 46, left: 96, fontSize: 28, letterSpacing: 4, fontWeight: 800}}>ALYSIA <span style={{color: P.muted, fontSize: 24, letterSpacing: 2, marginLeft: 20}}>逻辑游乐场 / 001</span></div>
    <div style={{position: 'absolute', right: 90, top: 37, display: 'flex', alignItems: 'center', gap: 9}}>{Array.from({length: 7}, (_, i) => <div key={i} style={{width: 14, height: 14, borderRadius: '50%', background: i < scene.races ? P.red : '#D8DCD5'}}/>)}<span style={{fontSize: 27, fontWeight: 800, marginLeft: 20}}>{scene.races ? `已用 ${scene.races} / 7 场` : '预算 7 场'}</span></div>
    <div style={{position: 'absolute', left: 96, right: 96, top: 102, height: 2, background: P.line}}/>
    <div style={{position: 'absolute', top: 144, left: 96, right: 80, fontSize: 66, fontWeight: 850, letterSpacing: -1, lineHeight: 1.22, opacity: entry, transform: `translateY(${(1 - entry) * 18}px)`}}>{scene.title}</div>
    <div style={{position: 'absolute', top: 246, left: 100, color: P.muted, fontSize: 29}}>{scene.kicker}</div>
    <div style={{position: 'absolute', top: 334, left: 100, width: 1270, height: 520, opacity: entry, transform: `translateY(${(1 - entry) * 20}px)`}}><SceneArt scene={scene} frame={frame}/></div>
    <Presenter scene={scene} frame={frame} entry={entry}/>
    <div style={{position: 'absolute', left: 1502, top: 892, width: 280, textAlign: 'center', color: P.muted, fontSize: 24, letterSpacing: 3}}>马娘的推理小课堂</div>
    {cue ? <div style={{position: 'absolute', left: 96, right: 96, bottom: 55, display: 'flex', justifyContent: 'center'}}><div style={{maxWidth: 1620, padding: '13px 30px', color: '#FFFDF6', backgroundColor: '#203442F0', borderRadius: 17, fontSize: 39, lineHeight: 1.45, fontWeight: 600, textAlign: 'center'}}>{cue.text}</div></div> : null}
    <div style={{position: 'absolute', left: 96, bottom: 17, color: P.muted, fontSize: 18}}>25 匹马 · 7 场比赛 · 找出前三</div>
    <div style={{position: 'absolute', right: 96, bottom: 17, color: P.muted, fontSize: 18}}>{scene.id} / 16</div>
  </AbsoluteFill>;
};

const Film = ({scenes, audio_file, duration_frames}) => {
  const frame = useCurrentFrame();
  return <AbsoluteFill style={{background: P.paper}}>{scenes.map(scene => <Sequence key={scene.id} from={scene.start_frame} durationInFrames={scene.duration_frames}><Scene scene={scene}/></Sequence>)}<Audio src={staticFile(audio_file)}/><div style={{position: 'absolute', left: 0, bottom: 0, height: 5, width: `${frame / duration_frames * 100}%`, background: P.red}}/></AbsoluteFill>;
};

const Root = () => {
  const props = getInputProps();
  return <Composition id="HorsePuzzle" component={Film} width={1920} height={1080} fps={30} durationInFrames={props.duration_frames || 30} defaultProps={props} calculateMetadata={({props: current}) => ({durationInFrames: current.duration_frames})}/>;
};

registerRoot(Root);

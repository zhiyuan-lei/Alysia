import React from 'react';
import {AbsoluteFill, Audio, Composition, Loop, OffthreadVideo, getInputProps, registerRoot, staticFile, useCurrentFrame} from 'remotion';

const BG = '#10152c';
const GOLD = '#f1cc83';
const clamp = n => Math.min(1, Math.max(0, n));
const smooth = n => {n = clamp(n); return n*n*(3-2*n);};
const P = ({x, y, w=740, size=32, color='#f4efdf', children, style={}}) =>
  <div style={{position:'absolute', left:x, top:y, width:w, fontSize:size, color, lineHeight:1.4, fontWeight:700, ...style}}>{children}</div>;

const Board = ({frame, scene, film}) => {
  const byId = Object.fromEntries(film.scenes.map(s=>[s.id,s]));
  const cue = (id, index=0) => byId[id].cues[index].start_frame;
  const remove = smooth((frame-cue('rules',1))/16);
  const coloring = smooth((frame-cue('color'))/26);
  const failure = frame>=byId.failure.start_frame && frame<byId.color.start_frame;
  const proof = frame>=byId.proof.start_frame;
  const localProof = Math.max(0, frame-byId.proof.start_frame);
  const proofLength = Math.max(24,byId.proof.duration_frames-36);
  const consumed = proof ? Math.min(30, Math.floor(clamp(localProof/proofLength)*30)) : 0;
  const shownPairs = Math.min(30, Math.floor(clamp((frame-byId.failure.start_frame)/Math.max(1, byId.failure.duration_frames-30))*30));
  const ending = ['answer','ending'].includes(scene.id);
  const pairLookup = new Map(film.board.pairs.flatMap((pair,index)=>pair.map(p=>[p.join(','),index])));
  const cells = [];
  for(let r=0;r<8;r++) for(let c=0;c<8;c++) {
    const gone = (r===0&&c===0)||(r===7&&c===7);
    const white = (r+c)%2===1;
    const pair = pairLookup.get(`${r},${c}`);
    const used = proof&&pair!==undefined&&pair<consumed;
    const appear = smooth((frame-(r*8+c)*.5)/12);
    const opacity = appear*(gone?1-remove:1)*(used?.1:1);
    const extra = !gone&&!pairLookup.has(`${r},${c}`);
    const x=64+c*58,y=148+r*58;
    cells.push(<g key={`${r}-${c}`}>
      <rect x={x+2} y={y+2} width={54} height={54} rx={4} fill='#b2a18a' opacity={opacity}/>
      <rect x={x+2} y={y+2} width={54} height={54} rx={4} fill={white?'#dce8f1':'#283753'} opacity={opacity*coloring} stroke={white?'#f5fbff':'#6b7f9e'} strokeWidth={1}/>
      {gone&&remove>0?<g opacity={remove}><rect x={x+3} y={y+3} width={52} height={52} rx={4} fill='#080a19' stroke='#f6907766' strokeDasharray='5 4'/><path d={`M${x+20} ${y+18}l18 22m-18 0l18-22`} stroke='#ef9d82' strokeWidth={3}/></g>:null}
      {extra&&(failure||proof)?<rect x={x+1} y={y+1} width={56} height={56} rx={5} fill='none' stroke='#ffd892' strokeWidth={3} opacity={.6+.35*Math.sin(frame/8)}/>:null}
    </g>);
  }
  const carpets = failure ? film.board.pairs.slice(0,shownPairs).map((pair,index)=>{
    const [a,b]=pair, r=Math.min(a[0],b[0]), c=Math.min(a[1],b[1]);
    const horizontal=a[0]===b[0];
    const x=64+c*58+6,y=148+r*58+6,w=horizontal?104:46,h=horizontal?46:104;
    const age=frame-byId.failure.start_frame-index*(byId.failure.duration_frames-30)/30;
    return <g key={index} opacity={smooth(age/8)} transform={`translate(0 ${-16*(1-smooth(age/10))})`}>
      <rect x={x} y={y+3} width={w} height={h} rx={6} fill='#050c1d' opacity={.4}/>
      <rect x={x} y={y} width={w} height={h} rx={6} fill={index%2?'#577f89':'#655e95'} stroke='#e7c784' strokeWidth={2}/>
      <rect x={x+5} y={y+5} width={w-10} height={h-10} rx={3} fill='none' stroke='#f3ddb466'/>
      <path d={`M${x+w/2} ${y+h/2-7}l7 7-7 7-7-7Z`} fill='#f4d491'/>
    </g>;
  }) : null;
  const black=30-consumed,white=32-consumed;
  return <g opacity={ending?.13:1}>
    <rect x={54} y={140} width={484} height={480} rx={15} fill='#070e22' stroke='#bea26b66' strokeWidth={2}/>
    {cells}{carpets}
    {failure?<g><text x={570} y={268} fill='#c8d8e4' fontSize={23}>已经铺下</text><text x={570} y={321} fill={GOLD} fontSize={51} fontWeight={800}>{shownPairs}<tspan fontSize={22}> 张</tspan></text><text x={570} y={377} fill='#c8d8e4' fontSize={22}>还剩 {31-shownPairs} 张</text><rect x={570} y={421} width={116} height={56} rx={7} fill='#665a94' stroke={GOLD} strokeWidth={2}/><path d='M619 435l10 14-10 14-10-14Z' fill={GOLD}/><text x={570} y={519} fill='#e4a897' fontSize={22}>{shownPairs===30?'这一张，放不下':'再试一次……'}</text></g>:null}
    {scene.id==='color'?<g><rect x={64+2*58+4} y={148+2*58+4} width={108} height={50} rx={6} fill='#eac67633' stroke={GOLD} strokeWidth={4}/><text x={568} y={287} fill={GOLD} fontSize={33}>1黑 + 1白</text><text x={568} y={331} fill='#c4d5e5' fontSize={22}>横着、竖着都一样</text></g>:null}
    {['imbalance','proof'].includes(scene.id)?<g>
      <rect x={565} y={216} width={190} height={220} rx={18} fill='#17243c' stroke='#6885a64d'/>
      <circle cx={592} cy={261} r={10} fill='#283753' stroke='#8498b3'/><text x={616} y={269} fill='#d0dce8' fontSize={23}>黑格</text>
      <text x={590} y={319} fill={GOLD} fontSize={49} fontWeight={800}>{black}</text>
      <circle cx={592} cy={358} r={10} fill='#dce8f1'/><text x={616} y={366} fill='#d0dce8' fontSize={23}>白格</text>
      <text x={590} y={416} fill='#f2f8ff' fontSize={49} fontWeight={800}>{white}</text>
      <text x={575} y={485} fill={GOLD} fontSize={26}>白格始终多2格</text>
      {proof?<text x={575} y={527} fill='#b7cbdf' fontSize={20}>两边都减 {consumed}</text>:null}
    </g>:null}
    {['promise','rules'].includes(scene.id)?<g><text x={568} y={268} fill={GOLD} fontSize={51} fontWeight={800}>31<tspan fontSize={23}>张</tspan></text><text x={568} y={311} fill='#c6d6e5' fontSize={22}>每张占相邻2格</text><path d='M570 351h142v58H570Z' fill='#655e95' stroke={GOLD} strokeWidth={2}/><path d='M641 352v56' stroke='#e7ce9b' strokeDasharray='4 4'/><text x={568} y={465} fill='#f4e1af' fontSize={28}>{remove>.8?'剩下 62 格':'原本 64 格'}</text></g>:null}
  </g>;
};

const Film = film => {
  const frame=useCurrentFrame();
  const scene=film.scenes.find(s=>frame>=s.start_frame&&frame<s.start_frame+s.duration_frames)||film.scenes[0];
  const subtitle=film.subtitles.find(s=>frame>=s.start_frame&&frame<s.end_frame);
  const ending=scene.id==='ending';
  return <AbsoluteFill style={{background:BG,fontFamily:'Microsoft YaHei, sans-serif'}}>
    <Loop durationInFrames={90}><OffthreadVideo src={staticFile(film.h3_file)} muted style={{width:1280,height:720}}/></Loop>
    <div style={{position:'absolute',inset:0,background:`linear-gradient(90deg,${BG} 59%,${BG}00 66%)`}}/>
    <svg width={1280} height={720} style={{position:'absolute',inset:0}}>
      <defs><radialGradient id='glow'><stop offset='0%' stopColor='#a787d8' stopOpacity='.15'/><stop offset='100%' stopColor='#a787d8' stopOpacity='0'/></radialGradient></defs>
      <ellipse cx={360} cy={390} rx={440} ry={330} fill='url(#glow)'/>
      {Array.from({length:16},(_,i)=><circle key={i} cx={30+(i*139)%710} cy={70+(i*101)%540} r={1+i%2} fill={GOLD} opacity={.1+.12*Math.sin(frame/30+i)}/>)}
      <Board frame={frame} scene={scene} film={film}/>
      <path d='M64 105h680' stroke={GOLD} strokeOpacity='.28'/>
    </svg>
    <P x={64} y={34} size={20} color={GOLD}>莉娅的奇幻谜题</P>
    <P x={64} y={65} size={32} w={730}>{scene.heading}</P>
    {scene.id==='answer'?<><P x={85} y={246} size={66} w={650} color={GOLD}>无解 ≠ 笨蛋</P><P x={90} y={356} size={29} w={630}>31张双格魔毯，需要31黑、31白。<br/>而这座桥，只剩30黑、32白。</P></>:null}
    {ending?<><P x={85} y={220} size={44} w={650} style={{lineHeight:1.65}}>先别急着<br/>责怪自己。</P><P x={90} y={400} size={30} w={650} color={GOLD}>也看看，有没有人<br/>偷偷烧掉了你的两格。</P></>:null}
    {subtitle?<P x={42} y={653} w={735} size={27} style={{padding:'9px 16px',boxSizing:'border-box',textAlign:'center',borderRadius:10,background:'#080f23e8',textShadow:'0 2px 3px #000'}}>{subtitle.text}</P>:null}
    <Audio src={staticFile(film.audio_file)}/>
  </AbsoluteFill>;
};

const defaults=getInputProps();
registerRoot(()=> <Composition id='LiaH3Bridge' component={Film} width={1280} height={720} fps={24}
  durationInFrames={defaults.duration_frames||1440} defaultProps={defaults}/>);

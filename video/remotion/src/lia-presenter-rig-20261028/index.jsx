import React from 'react';
import {AbsoluteFill,Audio,Composition,getInputProps,registerRoot,staticFile,useCurrentFrame} from 'remotion';
import {LiaPuppet} from './LiaPuppet.jsx';

const COLORS=['#DE967D','#8ABBC8','#D6B871','#B7A2CF','#8FB898'];
const clamp=n=>Math.max(0,Math.min(1,n));
const smooth=n=>{n=clamp(n);return n*n*(3-2*n);};
const FONT='Microsoft YaHei, sans-serif';

function Horse({x,y,color,label,small=false}){
  return <g transform={`translate(${x} ${y}) scale(${small?.58:1})`}>
    <ellipse cx="1" cy="49" rx="44" ry="7" fill="#10222D" opacity=".18"/>
    <path d="M-37 9Q-66 -5 -62 29" stroke={color} strokeWidth="10" fill="none" strokeLinecap="round"/>
    <ellipse cx="0" cy="16" rx="36" ry="22" fill={color}/>
    <path d="M17 9L22 -28Q37 -43 50 -23L57 -8Q53 8 36 10L26 23" fill={color}/>
    <path d="M28 -29L27 -48L38 -37M43 -32L49 -48L52 -29" fill={color}/>
    <path d="M19 -28Q11 -11 16 12M-18 29L-22 48M18 28L23 48" stroke={color} strokeWidth="10" strokeLinecap="round" fill="none"/>
    <path d="M23 -27Q20 -12 21 1" stroke="#5B554F" strokeWidth="6" fill="none"/>
    <circle cx="43" cy="-22" r="3" fill="#243742"/>
    <path d="M48 -4L54 -6" stroke="#6C6660" strokeWidth="2"/>
    <text x="-3" y="24" textAnchor="middle" fill="#FFFDF6" fontSize="22" fontFamily={FONT} fontWeight="800">{label}</text>
  </g>;
}

function PuzzleBoard({frame,data}){
  const s2=data.scenes[1].start_frame;
  const second=frame>=s2;
  const emphasis=data.scenes[1].start_frame+data.scenes[1].cues[1].start_frame;
  const challenge=frame>=emphasis;
  return <div style={{position:'absolute',left:70,top:150,width:1110,height:705}}>
    <svg width="1110" height="705" viewBox="0 0 1110 705">
      <defs><linearGradient id="board-paper" x2="0" y2="1"><stop stopColor="#F8F1DF"/><stop offset="1" stopColor="#E8E0CA"/></linearGradient></defs>
      <rect x="0" y="0" width="1110" height="705" rx="32" fill="url(#board-paper)"/>
      <path d="M45 125H1065M45 620H1065" stroke="#B3AE99" strokeWidth="2"/>
      <text x="50" y="78" fontFamily={FONT} fontSize="43" fill="#314F5A" fontWeight="800">{second?'只挑小组冠军，会漏掉谁？':'25匹马 · 5条跑道 · 没有秒表'}</text>
      {!second?<>
        {COLORS.map((c,r)=><g key={r}>{[0,1,2,3,4].map(i=><Horse key={i} x={115+i*178} y={185+r*83} color={c} label={`${'ABCDE'[r]}${i+1}`} small/>)}</g>)}
        <rect x="914" y="190" width="130" height="350" rx="22" fill="#314F5A"/>
        <text x="979" y="288" fontFamily={FONT} fontSize="85" fill="#EBC98C" textAnchor="middle" fontWeight="800">7</text>
        <text x="979" y="345" fontFamily={FONT} fontSize="28" fill="#FFFFFF" textAnchor="middle">场比赛</text>
        <path d="M941 390H1016M941 423H1016M941 456H1016" stroke="#8AABB0" strokeWidth="4"/>
        <text x="50" y="668" fontFamily={FONT} fontSize="31" fill="#516A70">怎样找到真正最快的3匹？</text>
      </>:<>
        {COLORS.map((c,i)=><Horse key={i} x={115+i*208} y={270} color={c} label={`${'ABCDE'[i]}1`}/>)}
        <path d="M75 350H1035" stroke="#AAA58F" strokeDasharray="9 12" strokeWidth="3"/>
        <text x="60" y="406" fontFamily={FONT} fontSize="31" fill="#637678">小组第一之间的顺序，还不能决定所有马的顺序</text>
        <Horse x={245} y={495} color={COLORS[0]} label="A2"/>
        <Horse x={755} y={495} color={COLORS[1]} label="B1"/>
        <text x="500" y="525" fontFamily={FONT} fontSize="65" fill={challenge?'#B96D64':'#566E75'} textAnchor="middle">？</text>
        {challenge?<g opacity={smooth((frame-emphasis)/12)}><rect x="55" y="190" width="1010" height="140" rx="22" stroke="#B97065" strokeWidth="5" fill="none" opacity=".8"/><text x="50" y="668" fontFamily={FONT} fontSize="31" fill="#A65E57">A2只输给A1，它也可能比B1更快。</text></g>:<text x="50" y="668" fontFamily={FONT} fontSize="31" fill="#516A70">先别急着把另外20匹马送回马厩。</text>}
      </>}
    </svg>
  </div>;
}

function Subtitle({frame,data}){
  const cue=data.subtitles.find(c=>frame>=c.start_frame&&frame<c.end_frame);
  return cue?<div style={{position:'absolute',left:80,right:80,bottom:33,textAlign:'center',color:'#FFFDF4',fontSize:39,fontWeight:650,fontFamily:FONT,textShadow:'0 2px 5px #000',padding:'10px 25px',background:'#142D42E8',borderRadius:15}}>{cue.text}</div>:null;
}

function PuzzleDemo(data){
  const frame=useCurrentFrame();
  return <AbsoluteFill style={{background:'radial-gradient(ellipse at 65% 30%,#396777,#173346 80%)',fontFamily:FONT,overflow:'hidden'}}>
    <div style={{position:'absolute',left:75,top:62,color:'#E5D7B7',fontSize:29}}>莉娅的谜题小课堂</div>
    <PuzzleBoard frame={frame} data={data}/>
    <LiaPuppet frame={frame} data={data} id="puzzle-lia" x={1235} y={62} scale={.48}/>
    <Subtitle frame={frame} data={data}/>
    <Audio src={staticFile(data.audio_file)}/>
  </AbsoluteFill>;
}

function Comparison(data){
  const frame=useCurrentFrame();
  return <AbsoluteFill style={{background:'#EDE8DC',fontFamily:FONT,overflow:'hidden'}}>
    <div style={{position:'absolute',left:0,top:0,width:960,height:'100%',background:'#E2E7E1'}}/>
    <div style={{position:'absolute',top:45,left:80,color:'#405D65',fontSize:35}}>同一套人物素材 · 静态基线</div>
    <div style={{position:'absolute',top:45,left:1040,color:'#405D65',fontSize:35}}>眨眼 · 语音嘴型 · 视线 · 点头</div>
    <LiaPuppet frame={frame} data={data} id="baseline-lia" x={160} y={65} scale={.48} animated={false}/>
    <LiaPuppet frame={frame} data={data} id="animated-lia" x={1120} y={65} scale={.48}/>
    <Subtitle frame={frame} data={data}/>
    <Audio src={staticFile(data.audio_file)}/>
  </AbsoluteFill>;
}

const data=getInputProps();
registerRoot(()=><>
  <Composition id="LiaPuzzleDemo" component={PuzzleDemo} width={1920} height={1080} fps={data.fps||30} durationInFrames={data.duration_frames||576} defaultProps={data}/>
  <Composition id="LiaComparison" component={Comparison} width={1920} height={1080} fps={data.fps||30} durationInFrames={data.duration_frames||576} defaultProps={data}/>
</>);

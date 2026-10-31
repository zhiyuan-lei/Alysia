import React from 'react';
import {AbsoluteFill, Audio, Composition, Img, registerRoot, staticFile, useCurrentFrame} from 'remotion';

const FPS = 24;
const clamp = x => Math.max(0, Math.min(1, x));
const ease = x => {x = clamp(x); return x*x*(3-2*x);};
const ramp = (t, a, b) => ease((t-a)/(b-a));
const mix = (a,b,p) => a+(b-a)*p;
const wrap = (value,period) => ((value%period)+period)%period;
const track = (t, keys) => {
  for(let i=1;i<keys.length;i++) if(t<keys[i][0]) return mix(keys[i-1][1],keys[i][1],ramp(t,keys[i-1][0],keys[i][0]));
  return keys[keys.length-1][1];
};

const DROPS = Array.from({length:420},(_,i)=>({x:(i*137.3)%2400-200,y:(i*97.7)%1400-160,s:11+(i%5)*4,a:.23+(i%4)*.07}));
const SPLASHES = Array.from({length:36},(_,i)=>({x:230+(i*139.7)%1510,y:800+(i*41)%220,phase:(i*.37)%1}));

function motion(t) {
  const x=track(t,[[0,1510],[2.4,1360],[5.2,1080],[7.1,1080],[7.6,1130],[9.2,1130],[11.6,830],[15,830],[16.4,1060],[28,1060]]);
  const crouch=t>=10.8&&t<15.2;
  const wet=ramp(t,15,17)*(1-ramp(t,21.1,22.1));
  const giving=ramp(t,9.8,13.1);
  const second=ramp(t,20.6,22.5);
  return {x,crouch,wet,giving,second,blue:{x:mix(x-92,700,giving),y:mix(160,490,giving),w:560},warm:{x:mix(2050,1260,second),y:170,w:720}};
}

function camera(t) {
  if(t<2.4) return {x:675,y:825,z:2.45+.025*t};
  if(t<5.6) return {x:990,y:570,z:1.03};
  if(t<8.4) return {x:track(t,[[5.6,1080],[7.6,1130],[8.4,1130]]),y:475,z:1.75};
  if(t<10.8) return {x:685,y:800,z:2.3};
  if(t<15.2) return {x:790,y:700,z:1.43+.025*ramp(t,11.2,14)};
  if(t<20.6) return {x:1060,y:475,z:1.75};
  if(t<24.2) return {x:1120,y:475,z:1.58};
  const p=ramp(t,24.2,27.3);
  return {x:mix(1120,975,p),y:mix(475,565,p),z:mix(1.58,1.03,p)};
}

function Umbrella({x,y,w,warm=false,t,opacity=1}) {
  const sway=warm?Math.sin(t*1.1)*.5:Math.sin(t*2)*.7;
  const h=w*.22, r=w/2;
  const colors=warm?['#8D4B4D','#BA7770','#EBC18D']:['#1B4058','#315E78','#A3C9D1'];
  return <div style={{position:'absolute',left:x,top:y,transform:`rotate(${sway}deg)`,transformOrigin:'0 390px',opacity}}>
    <svg width={w+30} height="500" viewBox={`${-r-15} -30 ${w+30} 500`} style={{position:'absolute',left:-r-15,top:-30,overflow:'visible'}}>
      <path d="M0 12V390Q0 424 27 424Q52 424 52 397" stroke="#B89F78" strokeWidth="9" fill="none"/>
      <path d={`M${-r} ${h}Q${-r*.56} ${-h*.21} 0 0Q${r*.56} ${-h*.21} ${r} ${h}Q${r*.75} ${h*.8} ${r*.5} ${h}Q${r*.25} ${h*.8} 0 ${h}Q${-r*.25} ${h*.8} ${-r*.5} ${h}Q${-r*.75} ${h*.8} ${-r} ${h}Z`} fill={colors[0]} stroke={colors[2]} strokeWidth="3"/>
      <path d={`M0 0Q${-r*.12} ${h*.46} ${-r*.5} ${h}Q${-r*.25} ${h*.8} 0 ${h}Q${r*.25} ${h*.8} ${r*.5} ${h}Q${r*.12} ${h*.46} 0 0`} fill={colors[1]}/>
      <path d={`M0 -14V1M0 0Q${-r*.12} ${h*.46} ${-r*.5} ${h}M0 0Q${r*.12} ${h*.46} ${r*.5} ${h}`} stroke={colors[2]} strokeWidth="3" fill="none" opacity=".7"/>
      {warm?<g transform={`translate(180 ${h+5}) rotate(${Math.sin(t*3)*7})`}><path d="M0 0V40" stroke="#E3C596" strokeWidth="3"/><path d="M-12 42V57Q0 78 12 57V42" stroke="#E8BF72" strokeWidth="5" fill="none"/></g>:null}
    </svg>
  </div>;
}

function Flower({t,giving}) {
  const swing=(1-giving)*(23+Math.sin(t*10)*8+12*ramp(t,7,10));
  return <div style={{position:'absolute',left:675,top:930,transform:`rotate(${(1-giving)*Math.sin(t*11)*1.6}deg)`,transformOrigin:'0 0'}}>
    <svg width="250" height="300" viewBox="-125 -260 250 300" style={{position:'absolute',left:-125,top:-260,overflow:'visible'}}>
      <defs><linearGradient id="pot" x1="0" x2="1"><stop stopColor="#79543F"/><stop offset=".5" stopColor="#C29770"/><stop offset="1" stopColor="#715344"/></linearGradient><radialGradient id="petal"><stop stopColor="#D3ECFF"/><stop offset="1" stopColor="#5D9FCD"/></radialGradient></defs>
      <ellipse cy="5" rx="85" ry="13" fill="#071119" opacity=".5"/>
      <g transform={`rotate(${swing} 0 -50)`}>
        <path d="M0 -45Q-15 -120 0 -176" stroke="#6C9D8F" strokeWidth="7" fill="none"/>
        <path d="M-3 -94Q-72 -149 -59 -105Q-40 -74 -3 -94M-5 -121Q51 -173 49 -135Q32 -109 -5 -121" fill="#5C8A7F" stroke="#8DAF9A" strokeWidth="2"/>
        <g transform={`rotate(${(1-giving)*13} 0 -181)`}>{[0,1,2,3,4,5].map(i=><ellipse key={i} cx="0" cy="-207" rx="18" ry="34" fill="url(#petal)" stroke="#A6CDDD" strokeWidth="1.5" transform={`rotate(${i*60} 0 -177)`}/>)}<circle cy="-177" r="14" fill="#E7C481"/></g>
      </g>
      <path d="M-61 -62H61L48 0H-48Z" fill="url(#pot)" stroke="#624B42" strokeWidth="3"/>
      <ellipse cy="-61" rx="64" ry="13" fill="#C19A77"/><ellipse cy="-64" rx="54" ry="8" fill="#473D38"/>
      <path d="M-62 -57Q0 -42 62 -57" fill="none" stroke="#E2B58C" strokeWidth="4" opacity=".6"/>
    </svg>
  </div>;
}

function Actor({t,m}) {
  const walking=(t<5.2)||(t>9.2&&t<10.8)||(t>15.2&&t<16.4);
  const bob=walking?Math.abs(Math.sin(t*10))*8:0;
  const shiver=m.wet*Math.sin(t*38)*2.2;
  const h=m.crouch?550:620, w=h*2/3;
  const pose=m.crouch?'crouch':t<10.8?'walk':t<24.2?'worry':'relieved';
  const foot=m.crouch?940:920;
  const warmth=.77+.13*m.second;
  return <>
    <svg width="460" height="70" style={{position:'absolute',left:m.x-230,top:foot-25}}><ellipse cx="230" cy="30" rx={m.crouch?150:105} ry="15" fill="#07131C" opacity=".58"/></svg>
    <div style={{position:'absolute',left:m.x-w/2,top:foot-h-bob,width:w,height:h,transform:`translateX(${shiver}px) rotate(${m.crouch?-1.5:walking?Math.sin(t*10)*1.4:m.wet*Math.sin(t*32)*.3}deg)`,transformOrigin:'50% 97%'}}>
      <Img src={staticFile(`assets/lia_${pose}.png`)} style={{width:'100%',height:'100%',filter:`brightness(${warmth}) saturate(.83) drop-shadow(1px 6px 4px #07121E66)`}}/>
      {m.wet>.01?<svg width="100%" height="100%" viewBox="0 0 410 620" style={{position:'absolute',inset:0,opacity:m.wet*.6}}>{[0,1,2].map(i=><path key={i} d={`M${130+i*45} ${150+((t*45+i*49)%150)}q-4 7 0 12q5-3 0-12Z`} fill="#B9D8E6"/>)}</svg>:null}
    </div>
  </>;
}

function Rain({t,m,front=false}) {
  const mask=front?'rain-front-mask':'rain-rear-mask';
  const umbrellas=[m.blue,...(m.second>.01?[m.warm]:[])];
  return <svg width="1920" height="1080" style={{position:'absolute',inset:0,pointerEvents:'none',opacity:front?.85:.8}}>
    <defs><mask id={mask}><rect width="1920" height="1080" fill="white"/>{umbrellas.map((u,i)=>{const edge=u.y+u.w*.22;return <polygon key={i} points={`${u.x-u.w/2},${edge} ${u.x+u.w/2},${edge} ${u.x+u.w/2-180},1200 ${u.x-u.w/2-180},1200`} fill="black"/>;})}</mask></defs>
    <g mask={`url(#${mask})`}>{DROPS.filter((_,i)=>front?i%5===0:i%5!==0).map((d,i)=>{const y=wrap(d.y+t*(front?790:640),1350)-140,x=wrap(d.x-t*130,2400)-200;return <path key={i} d={`M${x} ${y}l${front?-19:-11} ${d.s*(front?2.1:1.6)}`} stroke="#BFD8EC" strokeWidth={front?2.4:1.2} opacity={d.a}/>;})}</g>
  </svg>;
}

function Puddles({t}) {
  return <svg width="1920" height="1080" style={{position:'absolute',inset:0}}>{SPLASHES.map((p,i)=>{const f=(t*1.8+p.phase)%1;return <ellipse key={i} cx={p.x} cy={p.y} rx={6+f*25} ry={2+f*5} stroke="#AFC5D1" strokeWidth="1.3" fill="none" opacity={(1-f)*.24}/>;})}</svg>;
}

function OwnerSleeve({m}) {
  const p=m.second;
  if(p===0)return null;
  const dx=(1-p)*760;
  return <svg width="1920" height="1080" style={{position:'absolute',inset:0,transform:`translateX(${dx}px)`}}>
    <path d="M1960 770Q1650 650 1380 580L1330 661Q1600 770 1940 880Z" fill="#253345" stroke="#435168" strokeWidth="4"/>
    <path d="M1380 580L1330 661L1293 643L1339 568Z" fill="#C5AE82"/>
    <path d="M1341 579Q1304 566 1270 581L1244 593Q1232 600 1245 610L1265 608Q1230 629 1251 641Q1276 647 1305 631L1330 636Z" fill="#D8B79F" stroke="#AD8875" strokeWidth="3"/>
  </svg>;
}

function Film() {
  const f=useCurrentFrame(),t=f/FPS,m=motion(t),cam=camera(t);
  const flash=Math.max(0,1-Math.abs(t-7.12)/.12)*.13;
  const endFade=1-ramp(t,27.75,28);
  return <AbsoluteFill style={{background:'#07121B',overflow:'hidden'}}>
    <div style={{position:'absolute',inset:0,opacity:endFade}}>
      <div style={{position:'absolute',width:1920,height:1080,transformOrigin:'0 0',transform:`translate(${960-cam.x*cam.z}px,${540-cam.y*cam.z}px) scale(${cam.z})`}}>
        <Img src={staticFile('assets/rain_street.png')} style={{position:'absolute',inset:0,width:1920,height:1080,objectFit:'cover',filter:'brightness(.77) saturate(.8)'}}/>
        <Puddles t={t}/><Rain t={t} m={m}/>
        <Flower t={t} giving={m.giving}/>
        <Umbrella {...m.blue} t={t}/>
        <Actor t={t} m={m}/>
        <OwnerSleeve m={m}/>
        <Umbrella {...m.warm} t={t} warm opacity={m.second}/>
        <Rain t={t} m={m} front/>
        <div style={{position:'absolute',inset:0,background:'radial-gradient(ellipse at 61% 40%,#F6CA8522,transparent 38%)',opacity:m.second}}/>
      </div>
      <div style={{position:'absolute',inset:0,background:'radial-gradient(ellipse at 50% 46%,transparent 33%,#04101A66 100%)'}}/>
      <div style={{position:'absolute',inset:0,background:'#D2ECFF',opacity:flash}}/>
    </div>
    <div style={{position:'absolute',top:0,left:0,right:0,height:60,background:'#050A0F'}}/>
    <div style={{position:'absolute',bottom:0,left:0,right:0,height:60,background:'#050A0F'}}/>
    <div style={{position:'absolute',right:35,bottom:18,color:'#83909D',fontSize:17,fontFamily:'Microsoft YaHei, sans-serif'}}>莉娅 · 本地叙事小样 · AI辅助画面</div>
    <Audio src={staticFile('audio/soundtrack.wav')}/>
  </AbsoluteFill>;
}

registerRoot(()=><Composition id="LiaCinematicTest" component={Film} width={1920} height={1080} fps={FPS} durationInFrames={FPS*28}/>);

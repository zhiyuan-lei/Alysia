import React from 'react';
import {AbsoluteFill, Audio, Composition, Img, Sequence, getInputProps, interpolate, registerRoot, spring, staticFile, useCurrentFrame} from 'remotion';

const C = {ink:'#F5F2E5',muted:'#AABBCB',gold:'#F2CC7D',aqua:'#80E8DF',red:'#FF999A',panel:'#091A30DE',line:'#779AB34A'};
const clamp = n => Math.max(0,Math.min(1,n));
const Star = ({size=60,color=C.gold}) => <svg width={size} height={size} viewBox="0 0 100 100"><path d="M50 3L62 34L96 38L70 60L78 94L50 76L22 94L30 60L4 38L38 34Z" fill={color} stroke="#FFF3C3" strokeWidth="3"/></svg>;
const Pill = ({children,color=C.aqua}) => <div style={{display:'inline-flex',padding:'12px 25px',border:`1px solid ${color}70`,borderRadius:40,color,background:`${color}12`,fontSize:29,fontWeight:700}}>{children}</div>;
const Pony = ({width=150,number}) => <div style={{position:'relative',width,height:width*.72}}><Img src={staticFile('assets/pony.png')} style={{width:'100%',height:'100%',objectFit:'contain',filter:'drop-shadow(0 4px 12px #80E8DF35)'}}/>{number ? <span style={{position:'absolute',right:0,bottom:0,fontSize:27,color:C.gold,fontWeight:850}}>{number}</span> : null}</div>;

export const Chest = ({number,inside=null,open=false,active=false,width=170,color=C.aqua}) => <div style={{position:'relative',width,height:width*1.02,flexShrink:0,filter:active?`drop-shadow(0 0 18px ${color}70)`:'none'}}>
  <svg width="100%" height="100%" viewBox="0 0 160 164" style={{overflow:'visible'}}>
    {open ? <><ellipse cx="80" cy="64" rx="57" ry="33" fill={`${color}12`}/><path d="M28 83L15 23M132 83L145 23M60 80L57 4M100 80L108 4" stroke={color} strokeWidth="2" opacity=".4"/></> : null}
    <g transform={open?'translate(0,-39) rotate(-7 80 62)':''}><path d="M17 67V49Q17 15 80 15Q143 15 143 49V67Z" fill="#163B4A" stroke={C.gold} strokeWidth="3"/><path d="M36 27V66M124 27V66" stroke="#D4AB64" strokeWidth="8"/><path d="M22 49H138" stroke="#97DAD8" opacity=".3" strokeWidth="2"/></g>
    <path d="M17 67H143V123Q143 129 136 129H24Q17 129 17 123Z" fill="#173A48" stroke={C.gold} strokeWidth="3"/>
    <path d="M37 68V129M123 68V129" stroke="#D4AB64" strokeWidth="8"/><rect x="70" y="68" width="20" height="22" rx="4" fill={C.gold}/><circle cx="80" cy="76" r="3" fill="#173A48"/>
    <text x="80" y="119" textAnchor="middle" fill="#FFF4D7" fontSize="34" fontWeight="900">{number}</text>
    <text x="80" y="158" textAnchor="middle" fill={C.muted} fontSize="20">{number}号箱</text>
  </svg>
  {open && inside!==null ? <div style={{position:'absolute',left:'31%',top:'1%',width:'38%',height:'38%',display:'flex',alignItems:'center',justifyContent:'center'}}><Star size={width*.43} color={color}/><span style={{position:'absolute',top:'14%',fontSize:width*.23,fontWeight:900,color:'#173342'}}>{inside}</span></div> : null}
</div>;

const Ring = ({ids,color=C.aqua,width=360,height=330,danger=false,opened=0}) => {
  const f=useCurrentFrame();
  const cx=width/2,cy=height/2,rx=width*.33,ry=height*.32;
  const pts=ids.map((_,i)=>({x:cx+rx*Math.cos(-Math.PI/2+i*2*Math.PI/ids.length),y:cy+ry*Math.sin(-Math.PI/2+i*2*Math.PI/ids.length)}));
  return <div style={{position:'relative',width,height}}><svg width={width} height={height} style={{position:'absolute',inset:0,overflow:'visible'}}><defs><marker id={`arrow-${ids.join('-')}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10Z" fill={color}/></marker></defs>{pts.map((a,i)=>{
    const b=pts[(i+1)%pts.length],dx=b.x-a.x,dy=b.y-a.y,len=Math.hypot(dx,dy)||1;
    if(ids.length===1)return <circle key={i} cx={a.x+24} cy={a.y+15} r="31" fill="none" stroke={color} strokeWidth="3"/>;
    return <line key={i} x1={a.x+dx/len*34} y1={a.y+dy/len*34} x2={b.x-dx/len*39} y2={b.y-dy/len*39} stroke={color} strokeWidth="3" strokeDasharray="7 6" strokeDashoffset={-f*.7} markerEnd={`url(#arrow-${ids.join('-')})`} opacity=".8"/>;
  })}</svg>{pts.map((p,i)=><div key={ids[i]} style={{position:'absolute',left:p.x-33,top:p.y-33,width:66,height:66,borderRadius:'50%',background:danger&&i>=opened?'#502936':'#113C48',border:`3px solid ${danger&&i>=opened?C.red:color}`,display:'flex',alignItems:'center',justifyContent:'center',fontSize:34,fontWeight:850,boxShadow:opened>i?`0 0 21px ${color}40`:'none'}}>{ids[i]}</div>)}</div>;
};

const Follow = ({scene,frame,returning}) => {
  const phase=scene.cues.filter(c=>c.start_frame<=frame).length;
  const opened=returning?(phase>=3?3:2):(phase>=5?1:0);
  return <div style={{position:'relative',height:530}}>
    <div style={{display:'flex',gap:230,alignItems:'center',justifyContent:'center',paddingTop:85}}>{[1,4,7].map((n,i)=><Chest key={n} number={n} inside={[4,7,1][i]} open={i<opened} active={i===Math.max(0,opened-1)} width={205}/>)}</div>
    <svg width="1280" height="490" style={{position:'absolute',inset:0,pointerEvents:'none'}}><defs><marker id="pathArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10Z" fill={C.gold}/></marker></defs><path d="M312 172H518M748 172H952" fill="none" stroke={C.gold} strokeWidth="5" markerEnd="url(#pathArrow)" opacity={opened?1:.15}/>{returning&&opened===3?<path d="M1048 305C1048 440 230 440 230 312" fill="none" stroke={C.aqua} strokeWidth="5" strokeDasharray="10 7" strokeDashoffset={-frame*.8} markerEnd="url(#pathArrow)"/>:null}</svg>
    <div style={{position:'absolute',left:0,right:0,bottom:16,textAlign:'center'}}><Pill color={returning?C.aqua:C.gold}>{returning?(opened===3?'3次开箱 → 找到1号星徽 → 回到起点':'接着按星徽编号走：4 → 7'):'规则：从自己的箱号出发，下一箱 = 刚看到的星徽号'}</Pill></div>
  </div>;
};

const Rows = ({children}) => <div style={{display:'flex',alignItems:'center',justifyContent:'center',gap:35,height:480}}>{children}</div>;
const Fraction = ({n=1,d=51}) => <span style={{display:'inline-flex',flexDirection:'column',alignItems:'center',verticalAlign:'middle',fontSize:47,lineHeight:1.25,minWidth:80}}><span style={{borderBottom:`3px solid ${C.gold}`,width:'100%',textAlign:'center'}}>{n}</span><span>{d}</span></span>;

const Art = ({scene,frame}) => {
  const phase=scene.cues.filter(c=>c.start_frame<=frame).length;
  if(scene.kind==='opening') return <div style={{padding:'38px 45px'}}><div style={{fontSize:108,fontWeight:900,lineHeight:1.2,color:C.gold}}>100<span style={{fontSize:45,color:C.ink,marginLeft:22}}>只小马</span></div><div style={{fontSize:45,marginTop:25}}>每匹只有 <span style={{fontSize:72,color:C.aqua,fontWeight:900}}>50</span> 次开箱机会</div><div style={{display:'flex',gap:12,marginTop:35}}>{[1,2,3,4,5,6].map(n=><Pony key={n} width={130}/>)}</div><div style={{marginTop:22}}><Pill color={C.red}>少一枚星徽，所有小马都无法回家</Pill></div></div>;
  if(scene.kind==='shuffle') return <Rows><div style={{display:'grid',gridTemplateColumns:'repeat(10, 68px)',gap:8}}>{Array.from({length:100},(_,i)=><div key={i} style={{height:39,borderRadius:'13px 13px 5px 5px',border:`1px solid ${C.gold}70`,background:'#154352',fontSize:21,display:'flex',alignItems:'center',justifyContent:'center',color:C.gold,opacity:.6+.4*Math.sin((i+frame/10)/12)**2}}>{i+1}</div>)}</div><div style={{width:350,textAlign:'center'}}><Star size={110}/><div style={{fontSize:40,fontWeight:850,margin:'20px 0'}}>100枚星徽</div><div style={{fontSize:29,color:C.muted,lineHeight:1.9}}>均匀随机打乱<br/>每箱一枚 · 编号唯一</div></div></Rows>;
  if(scene.kind==='rules') return <Rows>{[['提前商量','定好统一方法','入场后不再传话'],['每匹50次','独自进入森林','找到自己的编号'],['保持原样','不移动星徽','不留标记，关好箱子']].map(([t,a,b],i)=><div key={t} style={{width:350,padding:'30px 25px',height:380,background:'#123448',border:`1px solid ${C.line}`,borderRadius:28,opacity:phase>=i+1?1:.55}}><div style={{fontSize:58,color:C.gold,fontWeight:850}}>0{i+1}</div><div style={{fontSize:40,fontWeight:850,margin:'20px 0'}}>{t}</div><div style={{fontSize:28,lineHeight:1.9,color:C.muted}}>{a}<br/>{b}</div></div>)}</Rows>;
  if(scene.kind==='random') return <div style={{textAlign:'center',paddingTop:45}}><div style={{fontSize:39,color:C.muted}}>单匹成功 1/2，必须连续赢100次</div><div style={{fontSize:77,fontWeight:900,margin:'38px 0',color:C.gold}}>(1/2)<sup style={{fontSize:42}}>100</sup> ≈ 7.89 × 10<sup style={{fontSize:42}}>−31</sup></div><div style={{display:'flex',gap:8,justifyContent:'center',flexWrap:'wrap',width:1000,margin:'auto'}}>{Array.from({length:100},(_,i)=><div key={i} style={{width:16,height:16,borderRadius:20,background:i<(frame/4)%100?C.red:'#51647A'}}/>)}</div><div style={{fontSize:37,marginTop:40,color:phase>=6?C.aqua:C.muted}}>{phase>=6?'莉娅：数字也许能指路……':'任何一匹失败，全员通关就失败'}</div></div>;
  if(scene.kind==='follow'||scene.kind==='return') return <Follow scene={scene} frame={frame} returning={scene.kind==='return'}/>;
  if(scene.kind==='structure'||scene.kind==='cycles') return <div style={{paddingTop:25}}><div style={{display:'flex',gap:10,alignItems:'center',justifyContent:'center'}}>{[[[1,4,7],C.gold],[[2,8],C.aqua],[[3,5,9,10],'#C2B0FF'],[[6],C.red]].map(([ids,color])=><div key={ids.join()} style={{textAlign:'center'}}><Ring ids={ids} color={color} width={ids.length===1?210:335} height={340}/><Pill color={color}>{ids.length}口的环</Pill></div>)}</div><div style={{textAlign:'center',fontSize:32,marginTop:30,color:C.muted}}>{scene.kind==='cycles'?'每个编号都在唯一的环里 · 最长4口 ≤ 限额5次':'数字 = 路标；从自己的编号出发，最终回到自己'}</div></div>;
  if(scene.kind==='danger') return <Rows><Ring ids={[1,4,7,2,8,3]} color={C.red} width={600} height={470} danger opened={Math.min(5,Math.floor(frame/50)+1)}/><div style={{width:510}}><div style={{fontSize:83,fontWeight:900,color:C.red}}>6 &gt; 5</div><div style={{fontSize:40,fontWeight:850,margin:'22px 0'}}>最后一口，打不开了</div><div style={{fontSize:31,lineHeight:1.8,color:C.muted}}>1 → 4 → 7 → 2 → 8<br/><span style={{color:C.red}}>第6口：3号箱内才有1号星徽</span></div><div style={{marginTop:28}}><Pill color={C.red}>这个环里的6匹都会失败</Pill></div></div></Rows>;
  if(scene.kind==='condition') return <Rows>{[[false,'所有环 ≤ 50','42 + 33 + 25 = 100','全员找回星徽'],[true,'存在环 > 50','61 + 39 = 100','全员通关失败']].map(([bad,title,example,verdict])=><div key={title} style={{width:560,padding:'36px 30px',borderRadius:28,border:`2px solid ${bad?C.red:C.aqua}70`,background:'#123448'}}><div style={{fontSize:43,fontWeight:850,color:bad?C.red:C.aqua}}>{title}</div><div style={{display:'flex',gap:20,margin:'35px 0'}}>{(bad?[61,39]:[42,33,25]).map((n,i)=><div key={n} style={{width:bad?160:130,height:bad?160:130,borderRadius:'50%',border:`5px dashed ${bad&&i===0?C.red:C.aqua}`,display:'flex',alignItems:'center',justifyContent:'center',fontSize:52,color:bad&&i===0?C.red:C.aqua}}>{n}</div>)}</div><div style={{fontSize:25,color:C.muted}}>环长示例：{example}</div><div style={{fontSize:37,fontWeight:800,marginTop:25}}>{verdict}</div></div>)}</Rows>;
  if(scene.kind==='exclusive') return <div style={{textAlign:'center',paddingTop:50}}><div style={{display:'flex',alignItems:'center',justifyContent:'center',gap:50}}>{[0,1].map(i=><React.Fragment key={i}>{i?<span style={{fontSize:83}}>+</span>:null}<div style={{width:230,height:230,border:`6px dashed ${C.red}`,borderRadius:'50%',display:'flex',alignItems:'center',justifyContent:'center',fontSize:94,color:C.red,fontWeight:850}}>51</div></React.Fragment>)}<span style={{fontSize:72}}>= 102</span></div><div style={{fontSize:39,marginTop:50}}>森林只有 <span style={{color:C.gold,fontWeight:850}}>100</span> 口宝箱</div><div style={{marginTop:25}}><Pill>因此，长度51—100的长环不可能同时出现</Pill></div></div>;
  if(scene.kind==='count') return <div style={{textAlign:'center',paddingTop:40}}><div style={{fontSize:32,color:C.muted,marginBottom:45}}>总失败概率 = 所有危险长环的概率之和</div><div style={{display:'flex',alignItems:'center',justifyContent:'center',gap:29,color:C.gold,fontSize:57}}><Fraction d={51}/><span>+</span><Fraction d={52}/><span>+</span><span>⋯</span><span>+</span><Fraction d={100}/></div><div style={{fontSize:33,color:C.muted,lineHeight:1.8,marginTop:45}}>互不重叠，因此可以直接相加<br/><span style={{fontSize:27}}>计数依据：C(100,k) × (k−1)! × (100−k)! / 100! = 1/k</span></div><div style={{marginTop:22}}><Pill color={C.red}>这条1/k公式用于 k &gt; 50 的长环</Pill></div></div>;
  if(scene.kind==='probability') return <div style={{textAlign:'center',paddingTop:25}}><div style={{fontSize:43,color:C.muted}}>P(全员成功) = 1 − Σ<sub>k=51…100</sub> 1/k</div><div style={{fontSize:158,lineHeight:1.4,color:C.gold,fontWeight:900}}>31.18<span style={{fontSize:86}}>%</span></div><Pill color={phase>=5?C.red:C.aqua}>{phase>=5?'仍有约68.82%的失败风险，并非必胜':'一百匹一起成功，接近三分之一'}</Pill><div style={{fontSize:24,color:C.muted,marginTop:26}}>100箱的精确计算值；1−ln2 ≈ 30.69% 是大规模极限</div></div>;
  if(scene.kind==='portal') return <div style={{height:500,position:'relative',textAlign:'center'}}><div style={{position:'absolute',left:200,top:25,width:470,height:410,borderRadius:'50% 50% 35% 35%',background:`radial-gradient(ellipse,#A0FFF0${phase>=4?'88':'30'},#43C8E52A 45%,transparent 70%)`,boxShadow:phase>=4?'0 0 100px #70FFDC45':'none'}}/><div style={{position:'absolute',left:240,top:30,width:370,height:380,borderRadius:'50% 50% 8% 8%',border:`7px solid ${C.gold}`,background:'#80F2DB20',boxShadow:'inset 0 0 50px #80E8DF70'}}>{Array.from({length:12},(_,i)=><div key={i} style={{position:'absolute',left:20+(i*91)%320,top:20+(i*67-frame*.3+900)%330,opacity:.5+.5*Math.sin(frame/15+i)}}><Star size={20}/></div>)}</div><div style={{position:'absolute',left:100+clamp(frame/320)*270,top:225,transform:`translateY(${Math.sin(frame/8)*3}px)`}}><Pony width={210}/></div><div style={{position:'absolute',left:755,top:100,textAlign:'left'}}><div style={{fontSize:62,fontWeight:850,color:C.gold}}>最后一枚星徽</div><div style={{fontSize:39,margin:'30px 0'}}>月门，打开了。</div><Pill>本次故事：最长环47 ≤ 50</Pill><div style={{fontSize:25,color:C.muted,marginTop:28}}>虚构结局，不代表每次都能成功</div></div></div>;
  if(scene.kind==='insight') return <Rows>{[['单匹的机会','50%','保持不变'],['全员一起成功','31.18%','让成败产生联系']].map(([title,note,desc],i)=><div key={title} style={{width:550,padding:'45px 25px',textAlign:'center',background:'#123448',border:`1px solid ${C.line}`,borderRadius:28}}><div style={{fontSize:38}}>{title}</div><div style={{fontSize:98,fontWeight:900,color:i?C.gold:C.aqua,margin:'30px 0'}}>{note}</div><div style={{fontSize:31,color:C.muted}}>{desc}</div></div>)}</Rows>;
  return <div style={{textAlign:'center',paddingTop:45}}><div style={{fontSize:56,fontWeight:850,color:C.gold}}>如果限额从50次，变成30次？</div><div style={{display:'flex',alignItems:'center',justifyContent:'center',gap:60,margin:'30px 0'}}><Chest number="?" width={190}/><div style={{fontSize:105,color:C.aqua}}>?</div><Pony width={260}/></div><Pill>把你的推理留在评论区</Pill><div style={{fontSize:23,color:C.muted,marginTop:25}}>经典谜题来源：Curtin & Warshauer · The Locker Puzzle (2006)</div></div>;
};

const Presenter = ({scene,frame}) => {
  const cueIndex=Math.max(0,scene.cues.findLastIndex(c=>c.start_frame<=frame));
  const poses=[scene.pose,scene.pose==='wave'?'point':'explain',scene.kind==='danger'?'surprise':'point',scene.kind==='portal'?'celebrate':'reveal'];
  const stride=Math.max(1,Math.ceil(scene.cues.length/4));
  const action=Math.min(3,Math.floor(cueIndex/stride));
  const pose=poses[action];
  const age=frame-(scene.cues[action*stride]?.start_frame||0);
  const fade=clamp(age/7);
  const previous=poses[Math.max(0,action-1)];
  const y=pose==='celebrate'?-Math.abs(Math.sin(age/10))*20*Math.exp(-age/70):Math.sin(frame/20)*2;
  const rotation=pose==='think'?-2.3:pose==='wave'?Math.sin(age/9)*2.5*Math.exp(-age/140):pose==='surprise'?Math.sin(Math.PI*clamp(age/32))*5:-.6;
  const style={position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'contain',filter:'drop-shadow(0 4px 20px #64BFD940)'};
  return <div style={{position:'absolute',left:1455,top:300,width:375,height:620,transform:`translateY(${y}px) rotate(${rotation}deg)`,transformOrigin:'50% 95%'}}><div style={{position:'absolute',left:45,right:45,bottom:15,height:25,background:'#00000055',borderRadius:'50%',filter:'blur(10px)'}}/>{action>0&&fade<1?<Img src={staticFile(`assets/presenter_${previous}.png`)} style={{...style,opacity:1-fade}}/>:null}<Img src={staticFile(`assets/presenter_${pose}.png`)} style={{...style,opacity:action>0?fade:1}}/>{pose==='surprise'?<div style={{position:'absolute',left:20,top:20,fontSize:75,color:C.gold,fontWeight:900}}>!</div>:null}{pose==='celebrate'&&age<70?[0,1,2].map(i=><div key={i} style={{position:'absolute',left:15+i*140,top:100+(i%2)*45-age*.5,opacity:clamp((70-age)/35),transform:`rotate(${age*2}deg)`}}><Star size={28}/></div>):null}<div style={{position:'absolute',left:50,right:35,bottom:-15,textAlign:'center',fontSize:25,color:C.gold,letterSpacing:4}}>莉娅的谜题小屋</div></div>;
};

const Scene = ({scene}) => {
  const frame=useCurrentFrame();
  const entry=spring({frame,fps:30,config:{damping:28,stiffness:120}});
  const cue=scene.cues.find(c=>c.start_frame<=frame&&frame<c.end_frame);
  return <AbsoluteFill style={{backgroundColor:'#08172A',color:C.ink,fontFamily:'Microsoft YaHei, sans-serif'}}>
    <Img src={staticFile('assets/moon_forest.png')} style={{position:'absolute',width:'100%',height:'100%',objectFit:'cover',transform:`scale(${1.01+frame*.000008})`}}/>
    <AbsoluteFill style={{background:'linear-gradient(90deg,#06142A88,#06142A45 70%,#06142A10)'}}/>
    {Array.from({length:15},(_,i)=><div key={i} style={{position:'absolute',left:(i*137+53)%1890,top:(i*79-frame*.12+1500)%1000,width:i%3===0?4:2,height:i%3===0?4:2,borderRadius:8,background:C.gold,opacity:(.3+.3*Math.sin(frame/25+i)),boxShadow:'0 0 9px #FFE3A6'}}/>)}
    <div style={{position:'absolute',left:90,top:44,fontSize:25,fontWeight:700,letterSpacing:4,color:C.gold}}>莉娅的谜题小屋 <span style={{marginLeft:25,color:C.muted,fontSize:22,letterSpacing:2}}>森林谜题 / 002</span></div>
    <div style={{position:'absolute',right:90,top:43,fontSize:25,color:C.muted}}>星徽宝箱 · {scene.id} / 16</div>
    <div style={{position:'absolute',left:90,right:90,top:100,height:1,background:C.line}}/>
    <div style={{position:'absolute',left:90,top:142,fontSize:62,fontWeight:850,letterSpacing:1,opacity:entry,transform:`translateY(${(1-entry)*15}px)`,textShadow:'0 3px 20px #000000'}}>{scene.title}</div>
    <div style={{position:'absolute',left:94,top:239,fontSize:28,color:C.muted}}>{scene.kicker}</div>
    <div style={{position:'absolute',left:88,top:310,width:1300,height:560,border:`1px solid ${C.line}`,borderRadius:30,background:C.panel,boxShadow:'0 15px 55px #00000035',opacity:entry,transform:`translateY(${(1-entry)*15}px)`}}><Art scene={scene} frame={frame}/></div>
    <Presenter scene={scene} frame={frame}/>
    {cue?<div style={{position:'absolute',left:90,right:90,bottom:55,display:'flex',justifyContent:'center'}}><div style={{maxWidth:1620,padding:'12px 30px',fontSize:40,fontWeight:600,lineHeight:1.4,textAlign:'center',borderRadius:15,background:'#061426EF',border:`1px solid ${C.line}`,textShadow:'0 2px 3px #000'}}>{cue.text}</div></div>:null}
    <div style={{position:'absolute',left:95,bottom:18,fontSize:18,color:C.muted}}>随机排列 · 不移动星徽 · 不传话 · 全员成功才通关</div>
  </AbsoluteFill>;
};

const Film = ({scenes,audio_file,duration_frames}) => {
  const frame=useCurrentFrame();
  return <AbsoluteFill>{scenes.map(s=><Sequence key={s.id} from={s.start_frame} durationInFrames={s.duration_frames}><Scene scene={s}/></Sequence>)}<Audio src={staticFile(audio_file)}/><div style={{position:'absolute',left:0,bottom:0,width:`${frame/duration_frames*100}%`,height:4,background:C.gold}}/></AbsoluteFill>;
};
const Root = () => {const props=getInputProps();return <Composition id="MoonChests" component={Film} width={1920} height={1080} fps={30} durationInFrames={props.duration_frames||30} defaultProps={props} calculateMetadata={({props:p})=>({durationInFrames:p.duration_frames})}/>;};
registerRoot(Root);

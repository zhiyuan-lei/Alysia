import React from 'react';
import {AbsoluteFill,Audio,Composition,Img,Sequence,getInputProps,registerRoot,spring,staticFile,useCurrentFrame} from 'remotion';

const C={ink:'#F5F2E5',muted:'#ABBDCC',gold:'#F2CC7D',aqua:'#80E8DF',red:'#FF999A',panel:'#091A30DE',line:'#779AB34A'};
const clamp=n=>Math.max(0,Math.min(1,n));
const Pill=({children,color=C.aqua})=><div style={{display:'inline-flex',padding:'11px 23px',border:`1px solid ${color}70`,borderRadius:40,background:`${color}12`,fontSize:28,fontWeight:700,color}}>{children}</div>;
const Star=({size=38,color=C.gold})=><svg width={size} height={size} viewBox="0 0 100 100"><path d="M50 3L62 34L96 38L70 60L78 94L50 76L22 94L30 60L4 38L38 34Z" fill={color}/></svg>;
const Pony=({width=160})=><Img src={staticFile('assets/pony.png')} style={{width,height:width*.72,objectFit:'contain',filter:'drop-shadow(0 5px 15px #80E8DF35)'}}/>;

const Guard=({label='?',type=null,width=150,point=null})=><div style={{width,flexShrink:0,textAlign:'center'}}><svg width={width} height={width*1.2} viewBox="0 0 150 180">
  <ellipse cx="75" cy="169" rx="55" ry="9" fill="#020D1F80"/>
  <path d="M39 74L29 153Q75 180 121 153L111 74Z" fill="#4D6980" stroke="#B9D7E2" strokeWidth="3"/>
  <path d="M75 107L52 154H98Z" fill="#29485E"/><path d="M24 14L45 24Q75 5 105 24L126 14L119 74Q75 115 31 74Z" fill="#627F94" stroke="#B9D7E2" strokeWidth="3"/>
  <ellipse cx="54" cy="53" rx="25" ry="29" fill="#E9EEE7"/><ellipse cx="96" cy="53" rx="25" ry="29" fill="#E9EEE7"/>
  <circle cx="56" cy="53" r="12" fill="#263B55"/><circle cx="94" cy="53" r="12" fill="#263B55"/><circle cx="60" cy="48" r="4" fill="white"/><circle cx="98" cy="48" r="4" fill="white"/>
  <path d="M65 72L75 88L85 72Z" fill={C.gold}/><circle cx="75" cy="117" r="14" fill="#1A394B" stroke={C.gold} strokeWidth="2"/>
  <text x="75" y="123" textAnchor="middle" fill={C.gold} fontSize="19" fontWeight="800">{type||'?'}</text>
  {point?<path d={point==='right'?'M112 96Q146 80 147 55':'M38 96Q4 80 3 55'} fill="none" stroke="#B9D7E2" strokeWidth="13" strokeLinecap="round"/>:null}
</svg><div style={{fontSize:25,color:type==='假'?C.red:type==='真'?C.aqua:C.muted,fontWeight:700}}>{label}</div></div>;

export const Gate=({side='左',width=260,open=false,reveal=false,safe=false})=>{
  const f=useCurrentFrame();
  const color=reveal?(safe?C.aqua:C.red):C.gold;
  return <div style={{width,height:width*1.34,position:'relative',flexShrink:0,textAlign:'center'}}>
    <svg width={width} height={width*1.18} viewBox="0 0 200 236" style={{overflow:'visible'}}>
      <path d="M19 223V97Q19 13 100 13Q181 13 181 97V223Z" fill="#102639" stroke={color} strokeWidth="5"/>
      <path d="M32 216V99Q32 30 100 30Q168 30 168 99V216Z" fill={open?'#398B9C':'#17384A'} stroke={color} strokeWidth="2"/>
      {open?<><path d="M50 212L74 89M86 215L108 68M125 215L143 86" stroke="#B9FFEA" strokeWidth="13" opacity=".22"/>{[0,1,2,3,4,5].map(i=><circle key={i} cx={50+(i*37)%105} cy={60+(i*43-f*.25+1000)%140} r={i%2?2:3} fill="#FFF7C7"/>)}</>:<><path d="M100 34V216M55 55V214M145 55V214" stroke="#B4CDCD" strokeWidth="2" opacity=".25"/><path d="M78 113Q100 98 122 113L116 147H84Z" fill="#23495B" stroke={C.gold} strokeWidth="2"/><circle cx="100" cy="129" r="6" fill={C.gold}/></>}
      <path d="M10 221H190M18 231H182" stroke={color} strokeWidth="4" strokeLinecap="round"/>
    </svg>
    <div style={{fontSize:29,fontWeight:800,color}}>{side}门{reveal?(safe?' · 庭院':' · 迷宫'):''}</div>
  </div>;
};
const Doors=({reveal=false,safe='left',open=false,guards=false,width=250})=><div style={{display:'flex',gap:115,alignItems:'flex-end',justifyContent:'center'}}>{['left','right'].map((s,i)=><div key={s} style={{position:'relative'}}><Gate side={i?'右':'左'} width={width} reveal={reveal} safe={safe===s} open={open&&safe===s}/>{guards?<div style={{position:'absolute',left:-75,bottom:35}}><Guard label={i?'右守卫':'左守卫'} width={105}/></div>:null}</div>)}</div>;
const Arrow=({color=C.gold,reverse=false,width=120})=><svg width={width} height="50" viewBox="0 0 120 50" style={{transform:reverse?'rotate(180deg)':'none',flexShrink:0}}><path d="M4 25H111M91 8L113 25L91 42" fill="none" stroke={color} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round"/></svg>;

const Case=({scene,frame,truth})=>{
  const phase=scene.cues.filter(c=>c.start_frame<=frame).length;
  const second=phase>=4;
  return <div style={{padding:'28px 35px'}}>
    <div style={{display:'flex',alignItems:'center',justifyContent:'center',gap:28,height:200}}>
      <Guard type={truth?'真':'假'} label={truth?'真话者':'假话者'} point="right" width={140}/>
      <div style={{width:700,textAlign:'center'}}><Pill color={truth?C.aqua:C.red}>{truth?'另一位是假话者 → 他会指右门':'另一位是真话者 → 他本来会指左门'}</Pill><div style={{marginTop:25,fontSize:37,color:second?C.gold:C.muted,fontWeight:800}}>{truth?'如实转述 → 仍然指右门':second?'撒谎，改口 → 指向右门':'正确答案，还要经过一次撒谎'}</div></div>
    </div>
    <div style={{display:'flex',alignItems:'center',justifyContent:'center',gap:65,marginTop:5}}><Gate side="左" width={175} reveal safe/><div style={{textAlign:'center',width:330}}><div style={{fontSize:30,color:C.red,fontWeight:800}}>最后听到的方向</div><Arrow color={C.red} width={200}/><div style={{fontSize:26,color:C.muted}}>指向右门 ≠ 应该走右门</div></div><Gate side="右" width={175} reveal safe={false}/></div>
  </div>;
};

const Art=({scene,frame})=>{
  const phase=scene.cues.filter(c=>c.start_frame<=frame).length;
  if(scene.kind==='opening')return <div style={{paddingTop:25,textAlign:'center'}}><Doors guards width={250}/><div style={{marginTop:16}}><Pill color={C.gold}>两扇门 · 两位守卫 · 唯一一个问题</Pill></div><div style={{position:'absolute',left:70,top:350}}><Pony width={160}/></div></div>;
  if(scene.kind==='rules')return <div style={{padding:'30px 40px'}}><div style={{display:'flex',justifyContent:'center',alignItems:'center',gap:55}}><Guard label="身份未知" width={210}/><div style={{textAlign:'center',width:575}}><div style={{fontSize:54,fontWeight:850,color:C.gold}}>恰好一真一假</div><div style={{fontSize:31,lineHeight:1.9,marginTop:24,color:C.muted}}>两人都知道正确的门<br/>两人都知道对方的身份<br/>衣服、位置都不能当提示</div></div><Guard label="身份未知" width={210}/></div><div style={{textAlign:'center',marginTop:28}}><Pill>不能试门 · 只能向其中一位问一句</Pill></div></div>;
  if(scene.kind==='direct')return <div style={{padding:'35px 40px',textAlign:'center'}}><div style={{fontSize:48,fontWeight:850,marginBottom:30}}>“哪扇门能出去？”</div><div style={{display:'flex',justifyContent:'center',gap:32}}>{[[true,'给你正确方向',C.aqua],[false,'给你错误方向',C.red]].map(([truth,text,color])=><div key={text} style={{width:510,background:'#133447',border:`1px solid ${C.line}`,borderRadius:25,padding:'22px 25px',display:'flex',alignItems:'center',gap:28}}><Guard type={truth?'真':'假'} label="可能问到" width={135}/><div style={{fontSize:34,fontWeight:800,color}}>{text}</div></div>)}</div><div style={{marginTop:35}}><Pill color={C.red}>你不知道问到了谁，答案仍不确定</Pill></div></div>;
  if(scene.kind==='identity')return <div style={{paddingTop:33,textAlign:'center'}}><div style={{fontSize:47,fontWeight:850}}>“你是说真话的吗？”</div><div style={{display:'flex',justifyContent:'center',alignItems:'center',gap:100,margin:'25px 0'}}>{[true,false].map(truth=><div key={String(truth)} style={{display:'flex',alignItems:'center',gap:30}}><Guard type={truth?'真':'假'} label={truth?'真话者':'假话者'} width={160}/><div style={{fontSize:52,color:C.gold,fontWeight:850}}>“是”</div></div>)}</div><Pill color={C.red}>没有分辨身份，唯一机会却耗尽了</Pill></div>;
  if(scene.kind==='question')return <div style={{padding:'28px 55px',textAlign:'center'}}><div style={{fontSize:34,color:C.muted,marginBottom:20}}>向任意一位守卫问：</div><div style={{fontSize:51,fontWeight:850,lineHeight:1.62,color:C.gold}}>“如果我问<span style={{color:C.aqua}}>另一位守卫</span>，<br/>哪扇门通向月光庭院，<br/>他会指哪一扇？”</div><div style={{marginTop:24}}><Pill color={C.aqua}>听完答案，选他指向的另一扇门</Pill></div></div>;
  if(scene.kind==='truth'||scene.kind==='liar')return <Case scene={scene} frame={frame} truth={scene.kind==='truth'}/>;
  if(scene.kind==='merge')return <div style={{padding:'35px 45px',textAlign:'center'}}>{[['问到真话者','如实转述假话'],['问到假话者','歪曲对方真话']].map(([a,b])=><div key={a} style={{display:'flex',gap:25,alignItems:'center',justifyContent:'center',marginBottom:28}}><Pill>{a}</Pill><Arrow width={85}/><div style={{fontSize:34,width:285}}>{b}</div><Arrow width={85}/><Pill color={C.red}>右门 · 迷宫</Pill></div>)}<div style={{height:2,background:C.line,margin:'35px 15px'}}/><div style={{fontSize:49,fontWeight:850,color:C.gold}}>都指向错误的门 → 你反选左门</div><div style={{fontSize:28,color:C.muted,marginTop:24}}>左门安全仅为本次讲解示例</div></div>;
  if(scene.kind==='reversals')return <div style={{textAlign:'center',padding:'65px 20px'}}><div style={{display:'flex',alignItems:'center',gap:20,justifyContent:'center'}}>{[['正确方向',C.aqua],['说谎一次',C.red],['错误方向',C.red],['你再反选',C.gold],['安全门',C.aqua]].map(([text,color],i)=><React.Fragment key={text}>{i?<Arrow color={color} width={55}/>:null}<div style={{width:175,padding:'30px 8px',borderRadius:22,border:`2px solid ${color}70`,background:'#143547',fontSize:31,fontWeight:800,color}}>{text}</div></React.Fragment>)}</div><div style={{marginTop:65}}><Pill color={C.gold}>一次来自回答，一次来自你的行动</Pill></div><div style={{fontSize:29,color:C.muted,marginTop:30}}>不要把“转述”和“再次说谎”混为一谈</div></div>;
  if(scene.kind==='escape')return <div style={{paddingTop:15,position:'relative',textAlign:'center'}}><Doors width={260} reveal safe="left" open={phase>=3}/><div style={{position:'absolute',left:100+clamp(frame/190)*280,top:260,transform:`translateY(${Math.sin(frame/10)*3}px)`}}><Pony width={205}/></div><div style={{position:'absolute',right:95,top:160,fontSize:38,color:C.gold,fontWeight:850}}>他说：右门<br/><span style={{fontSize:28,color:C.aqua}}>莉娅：那就走左门</span></div><div style={{marginTop:18}}><Pill>没有识别身份，也能找到正确的门</Pill></div></div>;
  if(scene.kind==='mirror')return <div style={{padding:'30px 28px',display:'flex',gap:24}}>{['left','right'].map(safe=><div key={safe} style={{width:610,padding:'24px 8px',borderRadius:24,border:`1px solid ${C.line}`,background:'#123447',textAlign:'center'}}><div style={{fontSize:33,fontWeight:850,color:C.gold,marginBottom:20}}>{safe==='left'?'假设左门安全':'假设右门安全'}</div><div style={{display:'flex',justifyContent:'center',gap:55}}><Gate side="左" width={150} reveal safe={safe==='left'}/><Gate side="右" width={150} reveal safe={safe==='right'}/></div><div style={{fontSize:28,color:C.aqua,marginTop:20}}>{safe==='left'?'回答指右 → 你选左':'回答指左 → 你选右'}</div></div>)}</div>;
  return <div style={{textAlign:'center',padding:'38px 25px'}}><div style={{fontSize:50,fontWeight:850,color:C.gold}}>如果两位都是骗子呢？</div><div style={{display:'flex',justifyContent:'center',alignItems:'center',gap:75,margin:'18px 0'}}><Guard type="假" label="假话者" width={175}/><div style={{fontSize:115,color:C.aqua}}>?</div><Guard type="假" label="假话者" width={175}/></div><Pill>先检查原来的前提，再给出你的理由</Pill><div style={{fontSize:23,color:C.muted,marginTop:25}}>经典谜题参考：MIT Junction 2014 · Two Guards</div></div>;
};

const Presenter=({scene,frame})=>{
  const cue=Math.max(0,scene.cues.findLastIndex(c=>c.start_frame<=frame));
  const stride=Math.max(1,Math.ceil(scene.cues.length/4));
  const action=Math.min(3,Math.floor(cue/stride));
  const poses=[scene.pose,scene.pose==='wave'?'think':'point',scene.kind==='escape'?'celebrate':'explain',scene.kind==='escape'?'celebrate':'reveal'];
  const pose=poses[action],previous=poses[Math.max(0,action-1)];
  const age=frame-(scene.cues[action*stride]?.start_frame||0),fade=clamp(age/7);
  const y=pose==='celebrate'?-Math.abs(Math.sin(age/10))*20*Math.exp(-age/70):Math.sin(frame/20)*2;
  const rot=pose==='think'?-2.3:pose==='wave'?Math.sin(age/9)*2.5*Math.exp(-age/140):pose==='surprise'?Math.sin(Math.PI*clamp(age/32))*5:-.6;
  const style={position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'contain',filter:'drop-shadow(0 4px 20px #64BFD940)'};
  return <div style={{position:'absolute',left:1455,top:300,width:375,height:620,transform:`translateY(${y}px) rotate(${rot}deg)`,transformOrigin:'50% 95%'}}>{action>0&&fade<1?<Img src={staticFile(`assets/presenter_${previous}.png`)} style={{...style,opacity:1-fade}}/>:null}<Img src={staticFile(`assets/presenter_${pose}.png`)} style={{...style,opacity:action>0?fade:1}}/>{pose==='surprise'?<div style={{position:'absolute',left:20,top:20,fontSize:75,color:C.gold,fontWeight:900}}>!</div>:null}{pose==='celebrate'&&age<70?[0,1,2].map(i=><div key={i} style={{position:'absolute',left:15+i*140,top:100+(i%2)*45-age*.5,opacity:clamp((70-age)/35)}}><Star size={28}/></div>):null}<div style={{position:'absolute',left:50,right:35,bottom:-15,textAlign:'center',fontSize:25,color:C.gold,letterSpacing:4}}>莉娅的谜题小屋</div></div>;
};
const Scene=({scene})=>{
  const frame=useCurrentFrame(),entry=spring({frame,fps:30,config:{damping:28,stiffness:120}});
  const cue=scene.cues.find(c=>c.start_frame<=frame&&frame<c.end_frame);
  return <AbsoluteFill style={{backgroundColor:'#08172A',color:C.ink,fontFamily:'Microsoft YaHei, sans-serif'}}>
    <Img src={staticFile('assets/moon_castle.png')} style={{position:'absolute',width:'100%',height:'100%',objectFit:'cover',transform:`scale(${1.01+frame*.000008})`}}/>
    <AbsoluteFill style={{background:'linear-gradient(90deg,#06142A70,#06142A30 70%,#06142A08)'}}/>
    <div style={{position:'absolute',left:90,top:44,fontSize:25,fontWeight:700,letterSpacing:4,color:C.gold}}>莉娅的谜题小屋 <span style={{marginLeft:25,color:C.muted,fontSize:22}}>城堡谜题 / 003</span></div>
    <div style={{position:'absolute',right:90,top:43,fontSize:25,color:C.muted}}>真假守卫 · {scene.id} / 12</div>
    <div style={{position:'absolute',left:90,right:90,top:100,height:1,background:C.line}}/>
    <div style={{position:'absolute',left:90,top:142,fontSize:62,fontWeight:850,opacity:entry,textShadow:'0 3px 20px #000000'}}>{scene.title}</div>
    <div style={{position:'absolute',left:94,top:239,fontSize:28,color:C.muted}}>{scene.kicker}</div>
    <div style={{position:'absolute',left:88,top:310,width:1300,height:560,border:`1px solid ${C.line}`,borderRadius:30,background:C.panel,boxShadow:'0 15px 55px #00000035',opacity:entry,transform:`translateY(${(1-entry)*15}px)`}}><Art scene={scene} frame={frame}/></div>
    <Presenter scene={scene} frame={frame}/>
    {cue?<div style={{position:'absolute',left:90,right:90,bottom:55,display:'flex',justifyContent:'center'}}><div style={{maxWidth:1620,padding:'12px 30px',fontSize:40,fontWeight:600,lineHeight:1.4,textAlign:'center',borderRadius:15,background:'#061426EF',border:`1px solid ${C.line}`}}>{cue.text}</div></div>:null}
    <div style={{position:'absolute',left:95,bottom:18,fontSize:18,color:C.muted}}>恰好一真一假 · 双方知情 · 只能问一句</div>
  </AbsoluteFill>;
};
const Film=({scenes,audio_file,duration_frames})=>{const f=useCurrentFrame();return <AbsoluteFill>{scenes.map(s=><Sequence key={s.id} from={s.start_frame} durationInFrames={s.duration_frames}><Scene scene={s}/></Sequence>)}<Audio src={staticFile(audio_file)}/><div style={{position:'absolute',left:0,bottom:0,width:`${f/duration_frames*100}%`,height:4,background:C.gold}}/></AbsoluteFill>;};
const Root=()=>{const props=getInputProps();return <Composition id="MoonGates" component={Film} width={1920} height={1080} fps={30} durationInFrames={props.duration_frames||30} defaultProps={props} calculateMetadata={({props:p})=>({durationInFrames:p.duration_frames})}/>;};
registerRoot(Root);

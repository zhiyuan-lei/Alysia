import React from 'react';
import {AbsoluteFill,Audio,Composition,Img,Sequence,getInputProps,registerRoot,staticFile,useCurrentFrame} from 'remotion';
import {Ribbon,SeamMap,palette as C} from './ribbon';
const clamp=x=>Math.max(0,Math.min(1,x));
const ease=x=>{x=clamp(x);return x*x*(3-2*x);};
const when=(s,t)=>s.cues.find(c=>c.text.includes(t))?.start_frame??0;
const during=(s,f,a,b)=>clamp((f-when(s,a))/Math.max(1,when(s,b)-when(s,a)));
const Note=({children,color=C.blue})=><div style={{display:'inline-block',padding:'12px 26px',borderRadius:8,background:color+'25',color:C.ink,fontSize:32,fontWeight:750}}>{children}</div>;
export const Workshop=()=> <AbsoluteFill style={{background:C.paper}}>
  <svg width="1920" height="1080" style={{position:'absolute'}}><defs><pattern id="paperdots" width="32" height="32" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#D5C8AD" opacity=".32"/></pattern></defs><rect width="1920" height="1080" fill="url(#paperdots)"/><path d="M0 65Q950 195 1920 65" fill="none" stroke="#D2B887" strokeWidth="2"/>{[80,390,740,1120,1470,1810].map((x,i)=><g key={x} transform={`translate(${x},${80+Math.sin(x/1920*Math.PI)*65})`}><path d="M0 0V38" stroke="#C6AA75" strokeWidth="2"/><path d="M0 24L6 40L22 44L8 54L11 72L0 62L-13 72L-9 54L-22 44L-6 40Z" fill={i%2?'#EACB81':'#D4E6DB'} opacity=".6"/></g>)}<rect y="915" width="1920" height="165" fill="#E7D5B8"/><path d="M0 915H1920M0 954H1920M0 1040H1920" stroke="#D5BF9B" strokeWidth="3"/><path d="M130 944L220 953M1770 1012L1860 1021" stroke="#B0CBC6" strokeWidth="8" strokeLinecap="round"/></svg>
</AbsoluteFill>;
const Presenter=({s,f})=>{
  const cue=Math.max(0,s.cues.findLastIndex(c=>c.start_frame<=f)),stride=Math.max(1,Math.ceil(s.cues.length/3)),action=Math.min(2,Math.floor(cue/stride));
  const poses=[s.pose,s.kind==='ending'?'celebrate':'point',s.kind==='mystery'?'think':'explain'],pose=poses[action],age=f-(s.cues[action*stride]?.start_frame||0);
  const left=['mystery','control','changed'].includes(s.kind),small=['plainmap','twistmap'].includes(s.kind);
  const x=left?75:small?1630:s.kind==='ending'?1320:1510,w=small?220:310,h=small?370:520,y=small?525:390;
  return <div style={{position:'absolute',left:x,top:y,width:w,height:h,transform:`translateY(${pose==='celebrate'?-Math.abs(Math.sin(age/11))*10*Math.exp(-age/100):Math.sin(f/22)*2}px) rotate(${pose==='surprise'?-2.5:pose==='think'?1.5:0}deg)`}}><Img src={staticFile(`assets/presenter_${pose}.png`)} style={{width:'100%',height:'100%',objectFit:'contain',filter:'drop-shadow(0 10px 12px #46586A18)'}}/>{pose==='surprise'?<div style={{position:'absolute',left:10,top:0,fontSize:68,color:C.gold,fontWeight:900}}>!</div>:null}</div>;
};
const Art=({s,f})=>{
  const common={position:'absolute',top:290},rot=.35+f*.0012;
  if(s.kind==='mystery'){
    const p=during(s,f,'她沿着中线','咦');
    return <><div style={{...common,left:410}}><Ribbon width={1100} height={570} cut={p} angle={rot} scissors trace={p===1?clamp((f-when(s,'纸环竟然'))/200):0}/></div><div style={{position:'absolute',left:760,top:820}}><Note>{p<1?'沿中线，剪完整一圈':'还连着！只有1个环'}</Note></div></>;
  }
  if(s.kind==='control'){
    const p=during(s,f,'沿中线剪一圈','果然得到'),spread=ease((f-when(s,'果然得到'))/40);
    return <><div style={{...common,left:410}}><Ribbon width={1100} height={570} twist={false} cut={p} spread={spread} angle={.15} scissors/></div><div style={{position:'absolute',left:780,top:820}}><Note>{spread>.5?'普通环 → 2个分开的环':'不扭转，直接粘合'}</Note></div></>;
  }
  if(s.kind==='make')return <><div style={{position:'absolute',left:140,top:330}}><svg width="600" height="430" viewBox="0 0 600 430"><rect x="35" y="75" width="520" height="130" fill={C.blue} opacity=".6"/><path d="M35 140H555" stroke={C.ink} strokeWidth="2" strokeDasharray="8 7"/><text x="55" y="119" fontSize="30" fill={C.ink}>1</text><text x="55" y="187" fontSize="30" fill={C.ink}>2</text><text x="515" y="119" fontSize="30" fill={C.ink}>2</text><text x="515" y="187" fontSize="30" fill={C.ink}>1</text><path d="M410 45C585 5 618 240 442 240" stroke={C.purple} strokeWidth="5" fill="none"/><path d="M457 218L439 242L469 248" stroke={C.purple} strokeWidth="5" fill="none"/><text x="75" y="310" fontSize="66" fontWeight="800" fill={C.ink}>180° = 半圈</text><text x="75" y="365" fontSize="29" fill={C.muted}>一端翻转，再粘合同号端点</text></svg></div><div style={{position:'absolute',left:720,top:295}}><Ribbon width={720} height={510} angle={rot}/></div><div style={{position:'absolute',left:870,top:805}}><Note>莫比乌斯带</Note></div></>;
  if(s.kind==='trace'){
    const p=during(s,f,'一直走下去','它们在粘合后');
    return <><div style={{...common,left:250}}><Ribbon width={1150} height={560} trace={p} angle={rot}/></div><div style={{position:'absolute',left:530,top:815}}><Note>{p<.5?'沿带面走，不跨边缘':p<1?'经过原来纸带的另一面':'原先的正反两面，连成同一张面'}</Note></div></>;
  }
  if(s.kind==='plainmap'||s.kind==='twistmap')return <><div style={{position:'absolute',left:170,top:335}}><SeamMap twist={s.kind==='twistmap'} progress={s.kind==='twistmap'?during(s,f,'蓝半幅的末端','剪刀分开'):0}/></div><div style={{position:'absolute',left:1470,top:350,fontSize:55,color:C.ink,fontWeight:800}}>{s.kind==='plainmap'?'2个环':'1个环'}</div></>;
  if(s.kind==='cut'){
    const p=during(s,f,'真的沿中线剪完整一圈','顺着蓝半幅走');
    return <><div style={{...common,left:220}}><Ribbon width={1180} height={570} cut={p} scissors angle={rot} trace={p===1?during(s,f,'顺着蓝半幅走','看见了吗'):0}/></div><div style={{position:'absolute',left:480,top:825}}><Note>切口分开半幅，接缝仍把两者串起来</Note></div></>;
  }
  if(s.kind==='changed')return <><div style={{...common,left:440}}><Ribbon width={1070} height={570} cut={1} angle={rot}/></div><div style={{position:'absolute',left:800,top:805}}><Note>1个长环 · 已经是双面</Note></div><div style={{position:'absolute',left:540,top:290,fontSize:30,color:C.muted}}>更长、更窄；有扭转，不等于仍然单面</div></>;
  if(s.kind==='second'){
    const p=during(s,f,'又沿新环的中线','这回终于');
    return <><div style={{...common,left:180}}><Ribbon width={1230} height={570} cut={1} second={p} separate={ease((f-when(s,'这回终于'))/45)} scissors angle={.35+f*.003}/></div><div style={{position:'absolute',left:510,top:825}}><Note color={C.gold}>{p<1?'沿新环的中线，再剪一圈':'蓝环 + 金环：两块纸，相互套连'}</Note></div></>;
  }
  return <><div style={{position:'absolute',left:120,top:300}}><Ribbon width={1130} height={570} cut={1} second={1} separate={1} angle={.55+f*.002}/></div><div style={{position:'absolute',left:310,top:810}}><Note color={C.gold}>星灯节展品：纸环的连接魔法</Note></div><div style={{position:'absolute',left:1290,top:305,fontSize:40,fontWeight:800,color:C.ink}}>你在哪一步<br/>猜错了？</div></>;
};
const Scene=({s})=>{
  const f=useCurrentFrame(),cue=s.cues.find(c=>c.start_frame<=f&&f<c.end_frame);
  return <AbsoluteFill style={{fontFamily:'Microsoft YaHei, sans-serif',color:C.ink}}><Workshop/><div style={{position:'absolute',left:75,top:40,fontSize:25,fontWeight:700,letterSpacing:3}}>莉娅的谜题小屋 <span style={{marginLeft:22,color:C.muted,fontSize:22}}>魔法实验 / 004</span></div><div style={{position:'absolute',right:75,top:40,fontSize:24,color:C.muted}}>纸环工坊 · {s.id} / 10</div><div style={{position:'absolute',left:95,top:175,fontSize:61,fontWeight:850}}>{s.title}</div><div style={{position:'absolute',left:100,top:265,fontSize:29,color:C.muted}}>{s.kicker}</div><Art s={s} f={f}/><Presenter s={s} f={f}/>{cue?<div style={{position:'absolute',left:95,right:95,bottom:61,textAlign:'center'}}><span style={{display:'inline-block',padding:'11px 28px',background:'#FFF9EEED',borderRadius:13,fontSize:39,fontWeight:650,lineHeight:1.45,boxShadow:'0 2px 8px #8D795D12'}}>{cue.text}</span></div>:null}<div style={{position:'absolute',left:100,bottom:20,fontSize:18,color:C.muted}}>薄纸带模型 · 沿长度方向中线剪切 · 不重新粘合</div></AbsoluteFill>;
};
const Film=({scenes,audio_file,duration_frames})=>{const f=useCurrentFrame();return <AbsoluteFill>{scenes.map(s=><Sequence key={s.id} from={s.start_frame} durationInFrames={s.duration_frames}><Scene s={s}/></Sequence>)}<Audio src={staticFile(audio_file)}/><div style={{position:'absolute',bottom:0,left:0,height:4,width:`${f/duration_frames*100}%`,background:C.blue}}/></AbsoluteFill>;};
const Root=()=>{const p=getInputProps();return <Composition id="MobiusWorkshop" component={Film} width={1920} height={1080} fps={30} durationInFrames={p.duration_frames||30} defaultProps={p} calculateMetadata={({props})=>({durationInFrames:props.duration_frames})}/>;};
registerRoot(Root);

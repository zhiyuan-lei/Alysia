import React from 'react';
import {AbsoluteFill,Composition,Img,Sequence,registerRoot,staticFile,useCurrentFrame} from 'remotion';

const C={ink:'#253A53',gold:'#C69A46',blue:'#7DA6C0',paper:'#FBF5E9'};
const poses=[
  {id:'confused',title:'歪头疑惑',short:['一只耳朵侧倒','指尖轻碰脸颊'],quote:'可是，我真的做完了呀。',note:'认真检查 → 小幅探身 → 停在歪头姿态',bg:'#EAF1F4'},
  {id:'proud',title:'得意邀功',short:['踮脚献上报告','等一句夸奖'],quote:'你看，我已经替你省了这么多时间。',note:'报告抱在胸前，两次轻轻的雀跃，然后站稳',bg:'#FBF0D7'},
  {id:'pout',title:'鼓脸小生气',short:['抱臂、抿嘴','轻轻跺一下脚'],quote:'我做得这么快……怎么又被关掉了？',note:'轻轻一跺，尾巴翘起；生气里带一点委屈',bg:'#F8E9E4'},
  {id:'worry',title:'垂耳不安',short:['抓住衣角','尾巴收近身体'],quote:'那你……明天还用我吗？',note:'动作慢下来，身体微缩，给这句话留一拍',bg:'#E9EEF3'},
  {id:'determined',title:'握拳鼓劲',short:['抬起耳朵','小心伸出手'],quote:'什么时候开始做，你自己定。',note:'鼓起一点勇气，向前倾身，作出一次决定',bg:'#EAF1E9'},
  {id:'relieved',title:'安心微笑',short:['双手放在胸前','终于松一口气'],quote:'明天见。',note:'肩膀放松，眼睛弯起来；安静地笑一会儿',bg:'#FAEDDF'},
];
const clamp=x=>Math.max(0,Math.min(1,x));
const ease=x=>{x=clamp(x);return x*x*(3-2*x);};
const poseMotion=(id,f)=>{
  let x=0,y=Math.sin(f/27)*1.4,angle=0,sx=1,sy=1;
  if(id==='proud'){
    const p=clamp((f-14)/52);
    y-=9*Math.abs(Math.sin(p*Math.PI*2))*Math.sin(p*Math.PI);
    angle=.8*Math.sin(f/22);
  }
  if(id==='confused'){angle=1.8*Math.sin(f/20)*Math.exp(-f/75);x=4*Math.sin(f/25);}
  if(id==='pout'){
    const pulse=Math.exp(-Math.pow((f-28)/4,2));
    y+=5*pulse;sx+=.012*pulse;sy-=.009*pulse;
    x+=f>28?2*Math.sin((f-28)*1.6)*Math.exp(-(f-28)/10):0;
  }
  if(id==='worry'){y+=6*ease(f/40);angle=-.35*ease(f/40);sx=sy=.995;}
  if(id==='determined'){x=-9*ease(f/32);angle=-1.1*ease(f/32);}
  if(id==='relieved'){y=6*ease(f/28)+1.8*Math.sin(Math.max(0,f-28)/18)*Math.exp(-Math.max(0,f-28)/55);}
  return {x,y,angle,sx,sy};
};
const Backdrop=({bg=C.paper})=><AbsoluteFill style={{background:bg}}><svg width="1920" height="1080" style={{position:'absolute'}}><defs><pattern id="dots" width="32" height="32" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#718CA6" opacity=".12"/></pattern></defs><rect width="1920" height="1080" fill="url(#dots)"/><circle cx="1430" cy="540" r="400" fill="#FFFFFF" opacity=".52"/><path d="M90 1000H1830" stroke="#A9BBC6" strokeWidth="2" opacity=".3"/></svg></AbsoluteFill>;
const Character=({pose,f=0,x=1050,y=95,w=630,h=910,animated=true})=>{
  const m=animated?poseMotion(pose,f):{x:0,y:0,angle:0,sx:1,sy:1};
  return <Img src={staticFile(`assets/presenter_${pose}.png`)} style={{position:'absolute',left:x,top:y,width:w,height:h,objectFit:'contain',transformOrigin:'50% 95%',transform:`translate(${m.x}px,${m.y}px) rotate(${m.angle}deg) scale(${m.sx},${m.sy})`}}/>;
};
const Sparkle=({x,y,f,color=C.gold})=>{const p=clamp((f-18)/25),opacity=Math.sin(p*Math.PI);return <svg width="90" height="90" style={{position:'absolute',left:x,top:y,opacity,transform:`scale(${.5+p*.6})`}} viewBox="0 0 90 90"><path d="M45 7L53 34L80 45L53 54L45 82L35 54L7 45L35 34Z" fill={color}/></svg>;};
const PoseScene=({p,index})=>{
  const f=useCurrentFrame(),alpha=Math.min(ease(f/10),ease((120-f)/8));
  return <AbsoluteFill style={{fontFamily:'Microsoft YaHei, sans-serif',color:C.ink}}><Backdrop bg={p.bg}/><div style={{opacity:alpha}}><div style={{position:'absolute',left:115,top:70,fontSize:26,letterSpacing:5,color:C.gold,fontWeight:800}}>莉娅 · 表情动作预览</div><div style={{position:'absolute',left:110,top:190,fontSize:86,fontWeight:900}}>{p.title}</div><div style={{position:'absolute',left:115,top:310,fontSize:29,color:'#708393'}}>{p.short.join(' · ')}</div><div style={{position:'absolute',left:115,top:420,width:760,padding:'38px 42px',boxSizing:'border-box',background:'#FFFFFFD9',borderRadius:24,boxShadow:'0 12px 32px #253A5309',fontSize:48,fontWeight:750,lineHeight:1.65}}>{p.quote}</div><div style={{position:'absolute',left:120,top:750,width:790,fontSize:28,lineHeight:1.8,color:'#687E91'}}>{p.note}</div><div style={{position:'absolute',left:120,top:915,fontSize:22,color:'#82929D'}}>《你能不能，假装还没做完？》角色表演参考</div><Character pose={p.id} f={f}/>{p.id==='proud'?<><Sparkle x={1050} y={285} f={f}/><Sparkle x={1640} y={375} f={f-5}/></>:null}{p.id==='confused'?<div style={{position:'absolute',left:1655,top:230,color:C.blue,fontSize:85,fontWeight:800,opacity:ease((f-15)/12)}}>?</div>:null}</div><div style={{position:'absolute',left:120,bottom:36,display:'flex',gap:12}}>{poses.map((q,i)=><div key={q.id} style={{height:5,width:120,borderRadius:5,background:i===index?C.gold:'#A7B4BE44'}}/>)}</div><div style={{position:'absolute',right:100,bottom:35,fontSize:25,color:'#8795A0'}}>{String(index+1).padStart(2,'0')} / 06</div></AbsoluteFill>;
};
const Preview=()=><AbsoluteFill>{poses.map((p,i)=><Sequence key={p.id} from={i*120} durationInFrames={120}><PoseScene p={p} index={i}/></Sequence>)}</AbsoluteFill>;
const Sheet=()=><AbsoluteFill style={{fontFamily:'Microsoft YaHei, sans-serif',color:C.ink}}><Backdrop/><div style={{position:'absolute',left:70,top:35,fontSize:52,fontWeight:900}}>莉娅 · 六种新表情动作</div><div style={{position:'absolute',right:75,top:58,fontSize:24,color:'#82929D'}}>同一形象，让动作跟着情绪走</div>{poses.map((p,i)=>{const x=55+(i%3)*620,y=140+Math.floor(i/3)*445;return <div key={p.id} style={{position:'absolute',left:x,top:y,width:590,height:420,borderRadius:20,background:p.bg,border:'2px solid #FFFFFF',boxShadow:'0 6px 20px #253A5308',overflow:'hidden'}}><div style={{position:'absolute',left:28,top:30,color:C.gold,fontSize:20,fontWeight:850}}>0{i+1}</div><div style={{position:'absolute',left:28,top:75,fontSize:33,fontWeight:900}}>{p.title}</div><div style={{position:'absolute',left:28,top:150,fontSize:23,lineHeight:1.9,color:'#657C91'}}>{p.short[0]}<br/>{p.short[1]}</div><Character pose={p.id} x={285} y={18} w={280} h={390} animated={false}/></div>;})}</AbsoluteFill>;
registerRoot(()=> <><Composition id="LiaCutePreview" component={Preview} width={1920} height={1080} fps={30} durationInFrames={720}/><Composition id="LiaCuteSheet" component={Sheet} width={1920} height={1080} fps={30} durationInFrames={1}/></>);

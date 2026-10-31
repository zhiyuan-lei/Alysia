import React from 'react';
import {AbsoluteFill,Composition,Img,registerRoot,staticFile} from 'remotion';
const MiniGate=()=> <svg width="210" height="215" viewBox="0 0 200 220"><path d="M20 210V89Q20 10 100 10Q180 10 180 89V210Z" fill="#17384A" stroke="#F2CC7D" strokeWidth="5"/><path d="M100 18V208M55 47V208M145 47V208" stroke="#9CC1CC" strokeWidth="2" opacity=".4"/><path d="M78 110Q100 95 122 110L116 146H84Z" fill="#23495B" stroke="#F2CC7D" strokeWidth="2"/><text x="100" y="139" textAnchor="middle" fontSize="34" fontWeight="850" fill="#F2CC7D">?</text></svg>;
const Cover=()=> <AbsoluteFill style={{background:'#08172A',fontFamily:'Microsoft YaHei, sans-serif',color:'#FFF4D7'}}>
  <Img src={staticFile('assets/moon_castle.png')} style={{position:'absolute',width:'100%',height:'100%',objectFit:'cover'}}/>
  <AbsoluteFill style={{background:'linear-gradient(90deg,#06142AE8,#06142A85 65%,#06142A10)'}}/>
  <div style={{position:'absolute',left:58,top:145,fontSize:27,fontWeight:750,color:'#91DAD9',letterSpacing:3}}>莉娅的谜题小屋 · 城堡篇</div>
  <div style={{position:'absolute',left:54,top:211,fontSize:91,fontWeight:900}}>两扇魔法门</div>
  <div style={{position:'absolute',left:58,top:334,fontSize:78,fontWeight:900}}>只准问 <span style={{color:'#80E8DF'}}>1</span> 句！</div>
  <div style={{position:'absolute',left:62,top:455,fontSize:38,fontWeight:800}}>一真一假，怎么选出安全的门？</div>
  <div style={{position:'absolute',left:62,top:525,display:'flex',alignItems:'center',gap:32}}><MiniGate/><span style={{fontSize:73,color:'#F2CC7D'}}>?</span><MiniGate/></div>
  <div style={{position:'absolute',right:4,top:167,width:380,height:570}}><Img src={staticFile('assets/presenter_think.png')} style={{width:'100%',height:'100%',objectFit:'contain',filter:'drop-shadow(0 6px 25px #80E8DF50)'}}/></div>
</AbsoluteFill>;
const Wide=()=> <div style={{position:'absolute',left:0,top:-112.5,width:1200,height:900}}><Cover/></div>;
const Root=()=> <><Composition id="GatesCover" component={Cover} width={1200} height={900} fps={30} durationInFrames={1}/><Composition id="GatesCoverWide" component={Wide} width={1200} height={675} fps={30} durationInFrames={1}/></>;
registerRoot(Root);

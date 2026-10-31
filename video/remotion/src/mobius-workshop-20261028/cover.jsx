import React from 'react';
import {AbsoluteFill,Composition,Img,registerRoot,staticFile} from 'remotion';
import {Ribbon,palette as C,Scissors} from './ribbon';
const Cover=()=> <AbsoluteFill style={{background:C.paper,color:C.ink,fontFamily:'Microsoft YaHei, sans-serif'}}>
  <svg width="1200" height="900" style={{position:'absolute'}}><path d="M0 70Q600 170 1200 70" fill="none" stroke="#D2B887" strokeWidth="3"/>{[130,410,760,1080].map(x=><g key={x} transform={`translate(${x},${100+Math.sin(x/1200*Math.PI)*30})`}><path d="M0 0V30" stroke="#C6AA75" strokeWidth="3"/><path d="M0 20L8 39L30 44L12 58L17 80L0 67L-17 80L-12 58L-30 44L-8 39Z" fill="#EACB81"/></g>)}<rect y="760" width="1200" height="140" fill="#E7D5B8"/><path d="M0 790H1200M0 865H1200" stroke="#D5BF9B" strokeWidth="3"/></svg>
  <div style={{position:'absolute',left:72,top:185,fontSize:83,fontWeight:900}}>剪了一圈，</div>
  <div style={{position:'absolute',left:72,top:292,fontSize:80,fontWeight:900}}>怎么还连着？</div>
  <div style={{position:'absolute',left:78,top:397,fontSize:28,color:C.muted}}>莫比乌斯带 · 莉娅的魔法实验</div>
  <div style={{position:'absolute',left:65,top:445}}><Ribbon width={760} height={330} cut={1} trace={.8} angle={.2}/></div>
  <svg width="1200" height="900" style={{position:'absolute'}}><Scissors x={490} y={695} size={1.6} angle={-25}/></svg>
  <div style={{position:'absolute',right:18,top:208,width:355,height:560}}><Img src={staticFile('assets/presenter_surprise.png')} style={{width:'100%',height:'100%',objectFit:'contain',filter:'drop-shadow(0 10px 12px #46586A20)'}}/></div>
  <div style={{position:'absolute',left:78,bottom:38,fontSize:25,fontWeight:700,letterSpacing:4}}>莉娅的谜题小屋 / 魔法纸环工坊</div>
</AbsoluteFill>;
const Wide=()=> <div style={{position:'absolute',left:0,top:-112.5,width:1200,height:900}}><Cover/></div>;
const Root=()=> <><Composition id="MobiusCover" component={Cover} width={1200} height={900} fps={30} durationInFrames={1}/><Composition id="MobiusCoverWide" component={Wide} width={1200} height={675} fps={30} durationInFrames={1}/></>;
registerRoot(Root);

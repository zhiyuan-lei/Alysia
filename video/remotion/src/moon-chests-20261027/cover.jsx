import React from 'react';
import {AbsoluteFill,Composition,Img,registerRoot,staticFile} from 'remotion';
const Cover=()=> <AbsoluteFill style={{background:'#08172A',fontFamily:'Microsoft YaHei, sans-serif',color:'#FFF4D7'}}>
  <Img src={staticFile('assets/moon_forest.png')} style={{position:'absolute',width:'100%',height:'100%',objectFit:'cover'}}/>
  <AbsoluteFill style={{background:'linear-gradient(90deg,#06142AEE,#06142A99 60%,#06142A10)'}}/>
  <div style={{position:'absolute',left:58,top:149,fontSize:27,fontWeight:750,color:'#91DAD9',letterSpacing:3}}>莉娅的谜题小屋 · 森林篇</div>
  <div style={{position:'absolute',left:52,top:218,fontSize:94,fontWeight:900,letterSpacing:-1}}>女巫的 <span style={{color:'#F2CC7D'}}>100</span> 箱</div>
  <div style={{position:'absolute',left:55,top:349,fontSize:78,fontWeight:900}}>每匹只许开 <span style={{color:'#80E8DF'}}>50</span> 箱</div>
  <div style={{position:'absolute',left:60,top:479,fontSize:40,fontWeight:800}}>100只小马，怎么一起逃走？</div>
  <div style={{position:'absolute',left:60,top:574,display:'flex',gap:20}}>{[1,4,7].map((n,i)=><React.Fragment key={n}><div style={{width:145,height:106,border:'3px solid #F2CC7D',borderRadius:'35px 35px 10px 10px',background:'#164554',display:'flex',alignItems:'center',justifyContent:'center',fontSize:62,fontWeight:900,color:'#F2CC7D'}}>{n}</div>{i<2?<span style={{fontSize:45,paddingTop:22,color:'#80E8DF'}}>→</span>:null}</React.Fragment>)}</div>
  <div style={{position:'absolute',right:8,top:160,width:380,height:570}}><Img src={staticFile('assets/presenter_surprise.png')} style={{width:'100%',height:'100%',objectFit:'contain',filter:'drop-shadow(0 6px 25px #80E8DF50)'}}/></div>
  <div style={{position:'absolute',left:58,top:725,fontSize:24,color:'#AABBCB'}}>跟着星徽，找回回家的路</div>
</AbsoluteFill>;
const Wide=()=> <div style={{position:'absolute',left:0,top:-112.5,width:1200,height:900}}><Cover/></div>;
const Root=()=> <><Composition id="MoonCover" component={Cover} width={1200} height={900} fps={30} durationInFrames={1}/><Composition id="MoonCoverWide" component={Wide} width={1200} height={675} fps={30} durationInFrames={1}/></>;
registerRoot(Root);

import React from 'react';
import {AbsoluteFill, Composition, Img, registerRoot, staticFile} from 'remotion';

const Cover = () => <AbsoluteFill style={{background:'#F5F2E9',color:'#203442',fontFamily:'Microsoft YaHei, sans-serif'}}>
  <div style={{position:'absolute',left:66,top:53,fontSize:27,fontWeight:700,letterSpacing:4,color:'#6A777B'}}>莉娅的谜题小屋 · 001</div>
  <div style={{position:'absolute',left:65,top:145,fontSize:105,fontWeight:900,letterSpacing:2}}>25 匹马</div>
  <div style={{position:'absolute',left:61,top:286,fontSize:112,fontWeight:900,letterSpacing:-2}}>只跑 <span style={{color:'#DE715D'}}>7</span> 场！</div>
  <div style={{position:'absolute',left:69,top:450,fontSize:37,fontWeight:700}}>没有秒表，怎样选出最快的 3 匹？</div>
  <div style={{position:'absolute',left:69,top:534,display:'flex',gap:14}}>{Array.from({length:5},(_,i)=><div key={i} style={{width:112,height:111,background:'#FFFDF8',border:'2px solid #E3DFD2',borderRadius:16}}><Img src={staticFile('assets/pony.png')} style={{width:'100%',height:'100%',objectFit:'contain'}}/></div>)}</div>
  <div style={{position:'absolute',left:70,top:687,background:'#203442',color:'#FFFDF6',fontSize:31,fontWeight:700,padding:'13px 25px',borderRadius:13}}>五个小组冠军的前三，就一定对吗？</div>
  <div style={{position:'absolute',right:22,top:137,width:385,height:638}}><Img src={staticFile('assets/presenter_point.png')} style={{width:'100%',height:'100%',objectFit:'contain'}}/></div>
  <div style={{position:'absolute',left:70,right:70,bottom:65,height:3,background:'#DAD7CC'}}/>
</AbsoluteFill>;
const Root = () => <Composition id="PublishCover" component={Cover} durationInFrames={1} fps={30} width={1200} height={900}/>;
registerRoot(Root);

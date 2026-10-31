import React from 'react';
import {Img,staticFile} from 'remotion';

const clamp=x=>Math.max(0,Math.min(1,x));
const smooth=x=>{x=clamp(x);return x*x*(3-2*x);};
const ramp=(f,a,b)=>smooth((f-a)/(b-a));
const lerp=(a,b,p)=>a+(b-a)*p;
const track=(f,keys)=>{for(let i=1;i<keys.length;i++)if(f<keys[i][0])return lerp(keys[i-1][1],keys[i][1],ramp(f,keys[i-1][0],keys[i][0]));return keys[keys.length-1][1];};

export function performanceAt(frame,data){
  const fps=data.fps,t=frame/fps;
  let eyes=1;
  for(const center of data.blink_centers_seconds){
    const dt=t-center;
    if(dt>=-.075&&dt<0)eyes=Math.min(eyes,1-smooth((dt+.075)/.075));
    else if(dt>=0&&dt<=.105)eyes=Math.min(eyes,smooth(dt/.105));
  }
  const gazeX=track(t,[[0,-.5],[3.3,-.5],[3.7,0],[7.4,0],[8,-.62],[11.8,-.62],[12.3,0],[15.2,0],[15.7,-.45],[18,-.45],[18.5,0],[19.2,0]]);
  const gazeY=track(t,[[0,.06],[7.7,.06],[8.1,.14],[12.3,.14],[12.7,0],[19.2,0]]);
  const emphasis=ramp(t,12.8,13.1)*(1-ramp(t,14.1,14.5));
  const nod=[.72,4.0,8.8,14.7].reduce((sum,at)=>sum+(t>=at&&t<at+.65?Math.sin((t-at)/.65*Math.PI)*1.8:0),0);
  const headAngle=gazeX*1.8+Math.sin((t-13)*8)*emphasis*1.25;
  return {mouth:data.mouth_open[Math.min(frame,data.mouth_open.length-1)]||0,eyes,gazeX,gazeY,headAngle,nod,brow:emphasis,breath:Math.sin(t*1.5)*1.2};
}

function Eye({id,cx,cy,scale=1,open,gazeX,gazeY}){
  const upper=-46*open+6*(1-open),lower=47*open+6*(1-open);
  const shape=`M-72 3Q-39 ${upper-12*open} 7 ${upper}Q48 ${upper+4} 68 2Q43 ${lower} -3 ${lower}Q-53 ${lower} -72 3Z`;
  return <g transform={`translate(${cx} ${cy}) rotate(-7) scale(${scale})`}>
    <defs>
      <clipPath id={`${id}-lid`}><path d={shape}/></clipPath>
      <radialGradient id={`${id}-iris`} cx=".6" cy=".75"><stop stopColor="#70D4FF"/><stop offset=".45" stopColor="#329DE1"/><stop offset=".78" stopColor="#3365BA"/><stop offset="1" stopColor="#1D285F"/></radialGradient>
      <linearGradient id={`${id}-white`} x2="0" y2="1"><stop stopColor="#D4D7E5"/><stop offset=".45" stopColor="#FFFFFF"/></linearGradient>
    </defs>
    {open>.025?<>
      <path d={shape} fill={`url(#${id}-white)`}/>
      <g clipPath={`url(#${id}-lid)`}>
        <g transform={`translate(${gazeX*21} ${gazeY*13})`}>
          <ellipse cx="0" cy="3" rx="42" ry="54" fill={`url(#${id}-iris)`} stroke="#293B77" strokeWidth="3"/>
          <ellipse cx="0" cy="-2" rx="14" ry="31" fill="#182549"/>
          <path d="M-31 24Q0 48 29 24" stroke="#8CE6FF" strokeWidth="4" fill="none" opacity=".8"/>
          <ellipse cx="-13" cy="-20" rx="14" ry="18" fill="#FFFFFF" opacity=".95"/>
          <ellipse cx="18" cy="18" rx="7" ry="10" fill="#D7F8FF"/>
          <circle cx="20" cy="-31" r="4" fill="#FFFFFF"/>
        </g>
      </g>
      <path d={`M-73 3Q-39 ${upper-12*open} 7 ${upper}Q48 ${upper+4} 69 2`} fill="none" stroke="#49333B" strokeWidth="10" strokeLinecap="round"/>
      <path d={`M-71 3L-89 -8M-64 -10L-80 -25M54 -10L72 -19`} stroke="#49333B" strokeWidth="7" strokeLinecap="round"/>
      <path d={`M-54 ${lower*.75}Q0 ${lower+5} 49 ${lower*.75}`} fill="none" stroke="#BB7778" strokeWidth="2.5" opacity=".72"/>
    </>:<path d="M-72 2Q-10 24 66 -1M-63 5L-83 14M-53 11L-67 23" stroke="#49333B" strokeWidth="8" strokeLinecap="round" fill="none"/>}
  </g>;
}

function Face({id,p}){
  const w=lerp(23,38,p.mouth),h=lerp(3,45,p.mouth);
  return <svg width="1374" height="1145" viewBox="0 0 1374 1145" style={{position:'absolute',inset:0}}>
    <defs><clipPath id={`${id}-skin`}><path d="M411 748Q468 789 539 764Q622 777 660 672Q702 581 723 490Q756 612 835 655Q885 693 928 705Q926 838 851 923Q779 983 650 1004Q510 973 455 901Q421 855 411 748Z"/></clipPath></defs>
    <g clipPath={`url(#${id}-skin)`}>
      <path d={`M458 ${721-p.brow*13}Q514 ${699-p.brow*21} 570 ${715-p.brow*18}`} stroke="#B88754" strokeWidth="8" strokeLinecap="round" fill="none"/>
      <path d={`M739 ${687-p.brow*15}Q802 ${664-p.brow*23} 862 ${690-p.brow*15}`} stroke="#B88754" strokeWidth="8" strokeLinecap="round" fill="none"/>
      <Eye id={`${id}-left`} cx={529} cy={812} scale={1.04} open={p.eyes} gazeX={p.gazeX} gazeY={p.gazeY}/>
      <Eye id={`${id}-right`} cx={804} cy={781} scale={1.13} open={p.eyes} gazeX={p.gazeX} gazeY={p.gazeY}/>
      <g transform="translate(665 918) rotate(-7)">
        {p.mouth>.045?<>
          <path d={`M${-w} 0Q0 ${-10-p.mouth*7} ${w} 0Q${w*.8} ${h} 0 ${h}Q${-w*.8} ${h} ${-w} 0Z`} fill="#623747" stroke="#B57478" strokeWidth="2.7"/>
          <path d={`M${-w*.65} ${h*.69}Q0 ${h*.42} ${w*.65} ${h*.69}Q0 ${h*1.02} ${-w*.65} ${h*.69}Z`} fill="#D98B9C"/>
          {p.mouth>.24?<path d={`M${-w*.65} -1Q0 -6 ${w*.65} -1L${w*.53} 5Q0 7 ${-w*.53} 5Z`} fill="#FFF8F3"/>:null}
        </>:<path d="M-25 -1Q0 10 25 -4" stroke="#A8666D" strokeWidth="3.1" strokeLinecap="round" fill="none"/>}
      </g>
    </g>
  </svg>;
}

export function LiaPuppet({frame,data,id='lia',x=0,y=0,scale=.42,animated=true}){
  const p=animated?performanceAt(frame,data):{mouth:0,eyes:1,gazeX:0,gazeY:0,headAngle:0,nod:0,brow:0,breath:0};
  return <div style={{position:'absolute',left:x,top:y,width:1374,height:2174,transform:`scale(${scale})`,transformOrigin:'0 0'}}>
    <div style={{position:'absolute',left:95,top:800,width:1145,height:1374,transform:`scaleY(${1+p.breath*.0013})`,transformOrigin:'50% 85%'}}><Img src={staticFile('assets/torso.png')} style={{width:'100%',height:'100%'}}/></div>
    <div style={{position:'absolute',left:0,top:p.breath+p.nod*2,width:1374,height:1145,transform:`rotate(${p.headAngle}deg)`,transformOrigin:'650px 1000px'}}>
      <Img src={staticFile('assets/head.png')} style={{position:'absolute',inset:0,width:'100%',height:'100%'}}/>
      <Face id={id} p={p}/>
    </div>
  </div>;
}

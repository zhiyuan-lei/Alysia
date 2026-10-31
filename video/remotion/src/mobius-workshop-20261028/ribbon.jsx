import React from 'react';

export const palette={paper:'#FCF5E6',ink:'#21344C',muted:'#64717C',blue:'#4BABB7',pink:'#EA8E98',gold:'#D7A34C',purple:'#8266AE'};
const cap=x=>Math.max(0,Math.min(1,x));
export const Scissors=({x,y,angle=0,size=1})=><g transform={`translate(${x},${y}) rotate(${angle}) scale(${size})`} stroke={palette.ink} strokeWidth="3" fill="none" strokeLinecap="round"><circle cx="-17" cy="-12" r="8" fill={palette.gold}/><circle cx="-17" cy="12" r="8" fill={palette.gold}/><path d="M-10-8L27 17M-10 8L27-17"/><circle r="3" fill={palette.paper}/></g>;

// The same parametric surface is checked in validate_topology.py.
const point=(u,v,twist)=>twist?[(2.7+v*Math.cos(u/2))*Math.cos(u),(2.7+v*Math.cos(u/2))*Math.sin(u),v*Math.sin(u/2)]:[2.7*Math.cos(u),2.7*Math.sin(u),v];
export const Ribbon=({width=1000,height=560,twist=true,cut=0,second=null,separate=0,trace=0,angle=.35,spread=0,scissors=false})=>{
  const pull=second===null?0:cap(separate)*.42;
  let yExtent=0;
  for(let i=0;i<=144;i++)for(const sign of [-1,1]){
    const [x,y,z]=point(i*2*Math.PI/144,sign*(1+pull),twist);
    const b=Math.sin(angle)*(x+(!twist?sign*spread*3.8:0))+Math.cos(angle)*y;
    yExtent=Math.max(yExtent,Math.abs(b*.53-(z+(!twist?sign*spread*.6:0))*.85));
  }
  const scale=Math.min(width/(8.8+(!twist?spread*7:0)+pull*2),(height-90)/(2*yExtent));
  const project=([x,y,z])=>{
    const a=Math.cos(angle)*x-Math.sin(angle)*y,b=Math.sin(angle)*x+Math.cos(angle)*y;
    return [width/2+a*scale,height/2+(b*.53-z*.85)*scale,(b*.85+z*.53)];
  };
  const items=[],n=144;
  const pushPatch=(u0,u1,v0,v1,color,offset=[0,0,0])=>{
    const p=[[u0,v0],[u1,v0],[u1,v1],[u0,v1]].map(([u,v])=>project(point(u,v,twist).map((a,i)=>a+offset[i])));
    const light=.80+.17*Math.abs(Math.cos((u0+u1)/4));
    const shaded='#'+[1,3,5].map(i=>Math.round(parseInt(color.slice(i,i+2),16)*light).toString(16).padStart(2,'0')).join('');
    items.push({z:p.reduce((s,a)=>s+a[2],0)/4,node:<polygon points={p.map(a=>a.slice(0,2).join(',')).join(' ')} fill={shaded} stroke={shaded} strokeWidth=".7"/>});
  };
  for(let i=0;i<n;i++){
    const u0=i*2*Math.PI/n,u1=(i+1)*2*Math.PI/n,mid=(i+.5)/n;
    const gap=mid<cut?.055:0;
    if(second===null){
      for(const sign of [-1,1]){
        const lo=sign<0?-1:gap,hi=sign<0?-gap:1;
        const offset=!twist?[sign*spread*3.8,0,sign*spread*.6]:[0,0,0];
        pushPatch(u0,u1,lo,hi,sign>0?palette.blue:palette.pink,offset);
      }
    }else{
      const pg=mid/2<second?.045:0,ng=(mid+1)/2<second?.045:0;
      [[-1-pull,-.5-ng-pull,palette.gold],[-.5+ng,-.055,palette.blue],[.055,.5-pg,palette.blue],[.5+pg+pull,1+pull,palette.gold]].forEach(([a,b,c])=>pushPatch(u0,u1,a,b,c));
    }
  }
  if(trace>0){
    const samples=Math.ceil(cap(trace)*n*2);
    for(let i=0;i<samples;i++){
      const t0=i*4*Math.PI/(n*2),t1=Math.min((i+1)*4*Math.PI/(n*2),trace*4*Math.PI);
      const a=project(point(t0,.48,true)),b=project(point(t1,.48,true));
      items.push({z:(a[2]+b[2])/2+.012,node:<path d={`M${a[0]},${a[1]}L${b[0]},${b[1]}`} stroke={palette.ink} strokeWidth="4" fill="none" strokeLinecap="round"/>});
    }
    const a=project(point(trace*4*Math.PI,.48,true));
    items.push({z:a[2]+.015,node:<circle cx={a[0]} cy={a[1]} r="8" fill={palette.gold} stroke={palette.ink} strokeWidth="2"/>});
  }
  items.sort((a,b)=>a.z-b.z);
  let sc=null;
  if(scissors&&cut>0&&cut<1){const a=project(point(cut*2*Math.PI,0,twist)),b=project(point(cut*2*Math.PI+.02,0,twist));sc=<Scissors x={a[0]} y={a[1]} angle={Math.atan2(b[1]-a[1],b[0]-a[0])*180/Math.PI} size={1.15}/>;}
  if(scissors&&second!==null&&second>0&&second<1){const a=project(point(second*4*Math.PI,.5,true));sc=<Scissors x={a[0]} y={a[1]} size={1.1}/>;}
  return <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}><ellipse cx={width/2} cy={height-52} rx={width*.28} ry="17" fill="#BDA680" opacity=".12"/>{items.map((v,i)=><React.Fragment key={i}>{v.node}</React.Fragment>)}{sc}</svg>;
};

export const SeamMap=({twist=false,progress=0,width=1250})=>{
  const x0=180,x1=1050,yA=150,yB=310;
  const q=cap(progress),top=q<.5;
  const cx=top?x0+(x1-x0)*q*2:x0+(x1-x0)*(q-.5)*2,cy=top?yA:yB;
  return <svg width={width} height="490" viewBox="0 0 1250 490">
    {[['蓝半幅',palette.blue,yA],['粉半幅',palette.pink,yB]].map(([name,color,y],i)=><g key={name}><rect x={x0} y={y-38} width={x1-x0} height="76" fill={color} opacity=".65"/><text x="260" y={y+10} fontSize="31" fill={palette.ink}>{name}</text>{[[x0,i+1],[x1,twist?2-i:i+1]].map(([x,id])=><g key={x}><circle cx={x} cy={y} r="26" fill={palette.paper} stroke={palette.ink} strokeWidth="2"/><text x={x} y={y+11} textAnchor="middle" fontSize="30" fontWeight="700" fill={palette.ink}>{id}</text></g>)}</g>)}
    {twist?<><path d={`M${x1},${yA}C1190,150 1180,430 1040,430H200Q80,430 80,310H${x0}`} fill="none" stroke={palette.blue} strokeWidth="5" strokeDasharray="10 7"/><path d={`M${x1},${yB}C1200,310 1180,30 1040,30H200Q80,30 80,150H${x0}`} fill="none" stroke={palette.pink} strokeWidth="5" strokeDasharray="10 7"/></>:<><path d="M1050 150Q1160 150 1160 85Q1160 20 600 20Q80 20 80 85Q80 150 180 150" fill="none" stroke={palette.blue} strokeWidth="5" strokeDasharray="10 7"/><path d="M1050 310Q1160 310 1160 385Q1160 460 600 460Q80 460 80 385Q80 310 180 310" fill="none" stroke={palette.pink} strokeWidth="5" strokeDasharray="10 7"/></>}
    <path d={`M230 230H1000`} stroke={palette.ink} strokeWidth="3" strokeDasharray="8 9"/><text x="615" y="219" textAnchor="middle" fontSize="25" fill={palette.muted}>中线切口</text>
    {twist&&q>0&&q<1?<circle cx={cx} cy={cy} r="13" fill={palette.gold} stroke={palette.ink} strokeWidth="3"/>:null}
    <text x="615" y="478" textAnchor="middle" fontSize="25" fill={palette.muted}>{twist?'蓝 → 粉 → 蓝：首尾串成1环':'蓝接蓝，粉接粉：各自闭合成2环'}</text>
  </svg>;
};

import React from 'react';
import {AbsoluteFill, Img, OffthreadVideo, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

const palette = {
  background: '#111827',
  panel: '#1f2937',
  primary: '#f9fafb',
  secondary: '#cbd5e1',
  accent: '#67e8f9',
};

const base = {
  alignItems: 'center',
  background: `linear-gradient(135deg, ${palette.background}, #172554)`,
  color: palette.primary,
  display: 'flex',
  fontFamily: 'Microsoft YaHei, Noto Sans CJK SC, sans-serif',
  justifyContent: 'center',
  padding: 120,
};

const Heading = ({children}) => (
  <div style={{fontSize: 88, fontWeight: 800, lineHeight: 1.18, textAlign: 'center'}}>{children}</div>
);

const Body = ({children}) => (
  <div style={{color: palette.secondary, fontSize: 38, lineHeight: 1.55, marginTop: 40, maxWidth: 1400, textAlign: 'center'}}>
    {children}
  </div>
);

export const TitleScene = ({visual}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const scale = spring({frame, fps, config: {damping: 18}});
  return (
    <AbsoluteFill style={base}>
      <div style={{opacity: interpolate(frame, [0, 18], [0, 1], {extrapolateRight: 'clamp'}), transform: `scale(${scale})`}}>
        <Heading>{visual.title}</Heading>
        <Body>{visual.body}</Body>
      </div>
    </AbsoluteFill>
  );
};

export const TextScene = ({visual}) => (
  <AbsoluteFill style={base}>
    <div style={{borderLeft: `12px solid ${palette.accent}`, paddingLeft: 54}}>
      <Heading>{visual.title}</Heading>
      <Body>{visual.body}</Body>
    </div>
  </AbsoluteFill>
);

export const ImageScene = ({visual}) => (
  <AbsoluteFill style={{...base, padding: 72}}>
    {visual.asset_path && !visual.placeholder ? (
      <Img src={staticFile(visual.asset_path)} style={{height: '100%', objectFit: 'contain', width: '100%'}} />
    ) : (
      <div style={{alignItems: 'center', backgroundColor: palette.panel, border: '4px dashed #64748b', borderRadius: 36, display: 'flex', height: '75%', justifyContent: 'center', width: '80%'}}>
        <Heading>{visual.title || 'Image placeholder'}</Heading>
      </div>
    )}
  </AbsoluteFill>
);

export const DiagramScene = ({visual}) => (
  <AbsoluteFill style={base}>
    <Heading>{visual.title}</Heading>
    <svg aria-label="diagram" viewBox="0 0 1200 360" style={{height: 420, marginTop: 50, width: 1350}}>
      {[80, 460, 840].map((x, index) => (
        <g key={x}>
          <rect x={x} y="90" width="280" height="160" rx="30" fill={index === 1 ? '#155e75' : palette.panel} stroke={palette.accent} strokeWidth="5" />
          <text x={x + 140} y="180" textAnchor="middle" fill={palette.primary} fontSize="34">{['观察', '推理', '行动'][index]}</text>
          {index < 2 ? <path d={`M ${x + 285} 170 L ${x + 365} 170`} stroke={palette.accent} strokeWidth="8" /> : null}
        </g>
      ))}
    </svg>
  </AbsoluteFill>
);

export const QuoteScene = ({visual}) => (
  <AbsoluteFill style={base}>
    <div style={{color: palette.accent, fontSize: 160, lineHeight: 0.5}}>“</div>
    <div style={{fontSize: 62, fontWeight: 650, lineHeight: 1.45, maxWidth: 1400, textAlign: 'center'}}>{visual.body || visual.title}</div>
  </AbsoluteFill>
);

export const CodeScene = ({visual}) => (
  <AbsoluteFill style={base}>
    <pre style={{backgroundColor: '#020617', borderRadius: 28, color: '#a5f3fc', fontFamily: 'Consolas, monospace', fontSize: 38, lineHeight: 1.5, maxHeight: 720, overflow: 'hidden', padding: 70, whiteSpace: 'pre-wrap', width: 1450}}>
      {visual.body || visual.title}
    </pre>
  </AbsoluteFill>
);

export const ChartScene = ({visual}) => (
  <AbsoluteFill style={base}>
    <Heading>{visual.title}</Heading>
    <div style={{alignItems: 'flex-end', display: 'flex', gap: 80, height: 440, marginTop: 60}}>
      {[0.42, 0.7, 0.9, 0.62].map((value, index) => (
        <div key={value} style={{backgroundColor: index === 2 ? palette.accent : '#3b82f6', borderRadius: '18px 18px 0 0', height: `${value * 100}%`, width: 170}} />
      ))}
    </div>
  </AbsoluteFill>
);

export const SceneRenderer = ({scene}) => {
  if (scene.visual.video_asset_path) {
    return (
      <AbsoluteFill style={{backgroundColor: palette.background}}>
        <OffthreadVideo
          src={staticFile(scene.visual.video_asset_path)}
          muted={scene.visual.discard_source_audio !== false}
          style={{height: '100%', objectFit: 'cover', width: '100%'}}
        />
      </AbsoluteFill>
    );
  }
  const props = {visual: scene.visual};
  switch (scene.type) {
    case 'title': return <TitleScene {...props} />;
    case 'image': return <ImageScene {...props} />;
    case 'diagram': return <DiagramScene {...props} />;
    case 'quote': return <QuoteScene {...props} />;
    case 'code': return <CodeScene {...props} />;
    case 'chart': return <ChartScene {...props} />;
    default: return <TextScene {...props} />;
  }
};

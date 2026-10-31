import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile} from 'remotion';
import {SceneRenderer} from './components.jsx';
import {SubtitleLayer} from './subtitle-layer.jsx';

export const VideoComposition = ({audio_file, scenes, subtitles, subtitle_style}) => (
  <AbsoluteFill style={{backgroundColor: '#111827'}}>
    {scenes.map((scene) => (
      <Sequence key={scene.id} from={scene.start_frame} durationInFrames={scene.duration_frames}>
        <SceneRenderer scene={scene} />
      </Sequence>
    ))}
    <Audio src={staticFile(audio_file)} />
    <SubtitleLayer subtitles={subtitles} styleConfig={subtitle_style} />
  </AbsoluteFill>
);

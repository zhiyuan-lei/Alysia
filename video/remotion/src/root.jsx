import React from 'react';
import {Composition, getInputProps} from 'remotion';
import {VideoComposition} from './video-composition.jsx';

const fallback = {
  title: 'Alysia',
  width: 1920,
  height: 1080,
  fps: 30,
  duration_frames: 30,
  audio_file: 'audio/narration.wav',
  scenes: [],
  subtitles: [],
  subtitle_style: {font_size: 54, position: 'bottom', max_width: 0.82},
};

export const RemotionRoot = () => {
  const input = getInputProps();
  const props = {...fallback, ...input};

  return (
    <Composition
      id="VideoComposition"
      component={VideoComposition}
      durationInFrames={props.duration_frames}
      fps={props.fps}
      width={props.width}
      height={props.height}
      defaultProps={props}
      calculateMetadata={({props: current}) => ({
        durationInFrames: current.duration_frames,
        fps: current.fps,
        width: current.width,
        height: current.height,
      })}
    />
  );
};

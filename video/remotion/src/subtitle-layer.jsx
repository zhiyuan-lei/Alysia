import React from 'react';
import {Sequence} from 'remotion';

const verticalPosition = {
  bottom: {bottom: 72},
  center: {top: '45%'},
  top: {top: 72},
};

export const SubtitleLayer = ({subtitles, styleConfig}) => {
  const position = verticalPosition[styleConfig.position] ?? verticalPosition.bottom;
  return subtitles.map((subtitle) => (
    <Sequence key={subtitle.id} from={subtitle.start_frame} durationInFrames={subtitle.end_frame - subtitle.start_frame}>
      <div style={{alignItems: 'center', display: 'flex', justifyContent: 'center', left: 0, position: 'absolute', right: 0, ...position}}>
        <div style={{backgroundColor: 'rgba(2, 6, 23, 0.78)', borderRadius: 18, color: '#ffffff', fontFamily: 'Microsoft YaHei, Noto Sans CJK SC, sans-serif', fontSize: styleConfig.font_size, fontWeight: 650, lineHeight: 1.35, maxWidth: `${styleConfig.max_width * 100}%`, padding: '16px 30px', textAlign: 'center', whiteSpace: 'pre-wrap', wordBreak: 'break-word'}}>
          {subtitle.text}
        </div>
      </div>
    </Sequence>
  ));
};

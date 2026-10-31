"""Validate the finished video and summarize observed resources; no inference."""
import json
from pathlib import Path
import subprocess
import sys

run = Path(sys.argv[1]).resolve()
summary = json.loads((run / 'summary.json').read_text())
assert summary['status'] == 'GENERATED_PENDING_VISUAL_REVIEW'
stream = summary['ffprobe']['streams'][0]
assert (stream['width'], stream['height'], int(stream['nb_frames'])) == (1280, 720, summary['output_frames'])
assert abs(float(summary['ffprobe']['format']['duration']) - summary['output_frames'] / 24) < 0.001
stages = []
for phase in ['keyframe', 'encode', 'sample', 'decode']:
    data = json.loads((run / f'{phase}_resources.json').read_text())
    assert data['exit_code'] == 0 and data['stop_reason'] is None
    stages.append({'phase': phase, 'elapsed_seconds': data['elapsed'],
                   'gpu_sampled_peak_mib': max(s['gpu']['used_mib'] for s in data['samples']),
                   'process_rss_sampled_peak_mib': max(s['rss'] for s in data['samples']) / 1024**2,
                   'process_private_sampled_peak_mib': max(s['private'] for s in data['samples']) / 1024**2,
                   'system_ram_sampled_peak_mib': max(s['system_used'] for s in data['samples']) / 1024**2})
report = {'artifact': summary['artifact'], 'sha256': summary['sha256'], 'bytes': summary['bytes'],
          'format_validation': 'PASS', 'visual_blink_validation': 'PENDING_HUMAN_OR_AGENT_REVIEW',
          'stages': stages, 'stage_time_seconds': sum(s['elapsed_seconds'] for s in stages),
          'sampled_gpu_budget_pass': all(s['gpu_sampled_peak_mib'] <= 6144 for s in stages),
          'sampled_process_private_ram_budget_pass': all(s['process_private_sampled_peak_mib'] <= 24576 for s in stages),
          'measurement_note': 'Sample maxima at about 0.5 seconds plus nvidia-smi query overhead; not unsampled instantaneous bounds.'}
(run / 'validation.json').write_text(json.dumps(report, indent=2))
subprocess.run(['ffmpeg', '-nostdin', '-n', '-v', 'error', '-i', summary['artifact'],
                '-vf', 'crop=200:180:800:80,tile=8x7', '-frames:v', '1', str(run / 'eye_contact_sheet.png')], check=True)
print(json.dumps(report, indent=2))

# H3 reference blink 720p

Goal: Use the supplied reference image and existing H3 weights to generate an actual 1280x720, approximately 2-second blink video, without integrating Alysia.

## Phases
- Discovery and prompt: complete.
- Prepare bounded sequential runner and reference: complete.
- Real keyframe encode, multimodal encode, 20-step sample, tiled decode: complete; targeted last-keyframe retry PASS.
- Validate container, inspect eye motion, report resource samples: complete. Second video's 56-frame eye contact sheet confirms open -> fully closed -> reopened. Slow blink, not a fast natural blink.

## Decisions
- Native 1280x736 / 56 frames, crop 8 pixels top/bottom. First attempt trimmed to 48 frames; retry retains all 56 frames / 2.333 seconds to preserve the final open-eyed keyframe.
- Preserve input; prompt asks for one blink around the middle, otherwise still scene.
- Existing dynamic disk-backed runtime, separate processes per model family. Extra dynamic VRAM headroom 3 GiB for higher resolution; reserve-vram 2 GiB; no model downloads.
- 24 GiB configured budget unchanged. Cooperative stop on measured pressure, not forced termination.

## Errors
Attempt 1: LoadImage rejected an absolute path before inference. Fixed caller to set the experiment input directory in the isolated process and use a relative filename; no security-path check was disabled. Hypothesis expansion skipped because the exception identifies the exact invalid argument. Preserve failed run_20261001_225130.

Visual QA: run_20261001_225215 generated valid video but not a complete blink. One targeted retry will add the same reference as the last keyframe to constrain reopened eyes; inspect final native frame before deciding trim duration.

## New request: expanded motion

Goal: Make a longer 720p H3 shot from the same image with drifting petals, moving hair, one blink, visible small hand and leg actions.

- [x] Inspect last successful run and image source; verify GPU idle.
- [x] Extend only TEST_ONLY runner with aligned frame-count and frozen prompt options; create prompt_motion.txt.
- [x] Execute 90 frames (3.75 seconds), 20 steps, same beginning/end image constraints.
- [x] Validate video and resource samples; contact sheets show all motion categories. Delivery copy saved and hash verified.

Keep the previous successful video and all evidence.

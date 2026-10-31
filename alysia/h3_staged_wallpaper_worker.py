"""One GPU phase of the local H3 dynamic-wallpaper workflow.

This file is launched directly with the ComfyUI Python interpreter. Keeping each
phase in a fresh process is essential to the measured low-VRAM profile.
"""
from __future__ import annotations

import argparse
import faulthandler
import json
import os
from pathlib import Path
import sys
import threading


def run(phase: str, run_dir: Path) -> None:
    faulthandler.enable()
    settings = json.loads((run_dir / "job.json").read_text(encoding="utf-8"))
    comfyui_dir = Path(settings["comfyui_dir"])
    os.chdir(comfyui_dir)
    sys.path.insert(0, str(comfyui_dir))

    import comfy_aimdo.control

    if not comfy_aimdo.control.init(simple_vram_headroom=2 * 1024**3):
        raise RuntimeError("AIMDO initialization failed")
    import comfy.options

    comfy.options.enable_args_parsing()
    sys.argv = [sys.argv[0], "--enable-dynamic-vram", "--reserve-vram", "2",
                "--vram-headroom", "3", "--fast-disk", "--disable-pinned-memory",
                "--disable-async-offload"]
    import torch
    import nodes
    import folder_paths

    folder_paths.set_input_directory(str(run_dir))
    import comfy.memory_management
    import comfy.model_patcher
    import comfy.model_management as model_management

    if not comfy_aimdo.control.init_devices([(0, 3 * 1024**3)]):
        raise RuntimeError("AIMDO device initialization failed")
    comfy.memory_management.aimdo_enabled = True
    comfy.model_patcher.CoreModelPatcher = comfy.model_patcher.ModelPatcherDynamic
    torch.cuda.set_per_process_memory_fraction(0.5, 0)

    done = threading.Event()

    def watch_stop() -> None:
        while not done.wait(0.1):
            if (run_dir / "STOP").exists():
                model_management.interrupt_current_processing(True)
                return

    threading.Thread(target=watch_stop, daemon=True).start()
    try:
        with torch.inference_mode():
            if phase in {"keyframe", "decode"}:
                vae = nodes.VAELoader().load_vae(settings["video_vae"])[0]
                if not vae.patcher.is_dynamic():
                    raise RuntimeError("H3 VAE did not use dynamic patcher")
            if phase == "keyframe":
                image = nodes.LoadImage().load_image("reference_canvas.png")[0]
                latent = nodes.VAEEncodeTiled().encode(vae, image, 256, 64, 16, 8)[0]["samples"]
                if not torch.isfinite(latent).all():
                    raise ValueError("non-finite keyframe latent")
                torch.save(latent.cpu(), run_dir / "keyframe.pt")
            elif phase == "encode":
                import node_helpers
                from comfy_extras.nodes_minimax_h3 import EmptyMiniMaxH3LatentAV

                clip = nodes.CLIPLoader().load_clip(settings["text_encoder"], "minimax", "default")[0]
                if not clip.patcher.is_dynamic():
                    raise RuntimeError("H3 text encoder did not use dynamic patcher")
                image = nodes.LoadImage().load_image("reference_canvas.png")[0]
                tokens = clip.tokenize((run_dir / "prompt.txt").read_text(encoding="utf-8"),
                                       images=[image, image])
                conditioning = clip.encode_from_tokens_scheduled(tokens)
                latent = torch.load(run_dir / "keyframe.pt", map_location="cpu", weights_only=True)
                keyframes = [{"resolved_frame_index": 0, "latent": latent},
                             {"resolved_frame_index": settings["frames"] - 1, "latent": latent}]
                conditioning = node_helpers.conditioning_set_values(conditioning, {
                    "minimax_keyframes": keyframes,
                    "minimax_frame_count": settings["frames"],
                })
                empty = EmptyMiniMaxH3LatentAV.execute(1280, 736, settings["frames"])[0]
                video, audio = empty["samples"].unbind()
                if not all(torch.isfinite(item[0]).all() for item in conditioning):
                    raise ValueError("non-finite conditioning")
                torch.save({"conditioning": conditioning, "video": video, "audio": audio},
                           run_dir / "conditioning.pt")
            elif phase == "sample":
                from comfy.nested_tensor import NestedTensor
                from comfy_extras.nodes_custom_sampler import (
                    BasicScheduler, BasicGuider, KSamplerSelect, RandomNoise, SamplerCustomAdvanced,
                )

                data = torch.load(run_dir / "conditioning.pt", map_location="cpu", weights_only=True)
                model = nodes.UNETLoader().load_unet(settings["diffusion_model"], "default")[0]
                if not model.is_dynamic():
                    raise RuntimeError("H3 diffusion model did not use dynamic patcher")
                sigmas = BasicScheduler.execute(model, "simple", settings["steps"], 1.0)[0]
                guider = BasicGuider.execute(model, data["conditioning"])[0]
                noise = RandomNoise.execute(settings["seed"])[0]
                sampler = KSamplerSelect.execute("res_multistep")[0]
                samples = {"samples": NestedTensor((data["video"], data["audio"]))}
                result = SamplerCustomAdvanced.execute(noise, guider, sampler, sigmas, samples)[0]
                video, audio = result["samples"].unbind()
                if not torch.isfinite(video).all() or not torch.isfinite(audio).all():
                    raise ValueError("non-finite sampled latent")
                torch.save({"video": video.cpu(), "audio": audio.cpu()}, run_dir / "sampled.pt")
            elif phase == "decode":
                from PIL import Image

                data = torch.load(run_dir / "sampled.pt", map_location="cpu", weights_only=True)
                images = nodes.VAEDecodeTiled().decode(
                    vae, {"samples": data["video"]}, 256, 64, 16, 8,
                )[0]
                if list(images.shape) != [settings["frames"], 736, 1280, 3]:
                    raise ValueError(f"unexpected decoded frame shape: {list(images.shape)}")
                if not torch.isfinite(images).all():
                    raise ValueError("non-finite decoded image")
                for index, frame in enumerate(images):
                    pixels = (frame.clamp(0, 1).cpu().numpy() * 255).astype("uint8")
                    Image.fromarray(pixels).save(run_dir / f"frame_{index:03d}.png")
            else:
                raise ValueError(f"unknown phase: {phase}")
        print(json.dumps({"event": "PASS", "phase": phase,
                          "torch_peak_allocated": torch.cuda.max_memory_allocated(),
                          "torch_peak_reserved": torch.cuda.max_memory_reserved()}), flush=True)
    finally:
        done.set()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, choices=("keyframe", "encode", "sample", "decode"))
    parser.add_argument("--run-dir", required=True, type=Path)
    arguments = parser.parse_args()
    run(arguments.phase, arguments.run_dir.resolve())

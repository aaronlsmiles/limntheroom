# Models

Checkpoints and models are gitignored (`models/*.pt`, `models/*.task`). Download and verify:

| File | Source | SHA-256 | Size |
|---|---|---|---|
| `sam2.1_hiera_small.pt` | https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt | `6d1aa6f30de5c92224f8172114de081d104bbd23dd9dc5c58996f0cad5dc4d38` | 184,416,285 bytes |
| `hand_landmarker.task` | https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task | `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1` | 7,819,105 bytes |

URL taken from `checkpoints/download_ckpts.sh` in facebookresearch/sam2 at commit `2b90b9f5ceec907a1c18123530e92e794ad901a4`. Downloaded 31 Oct 2026.

```bash
curl -fL -o models/sam2.1_hiera_small.pt https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt
shasum -a 256 models/sam2.1_hiera_small.pt
```

Device: CPU. MPS support was never merged upstream.

The MediaPipe Hand Landmarker (float16, version 1) is Google's official model, linked from the MediaPipe Hand Landmarker guide (ai.google.dev, `mediapipe-models` bucket). The versioned `/1/` URL is used, not `/latest/`; on 31 Oct 2026 both served the same bytes. Downloaded 31 Oct 2026; used by `seam/cues/hands.py`.

```bash
curl -fL -o models/hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
shasum -a 256 models/hand_landmarker.task
```

## netG.pth (line extractor, not in this repo)

The lines job (`seam/lines_job.py`) uses StillDrawn's frozen line extractor, AnimeLineArt `netG.pth`, read in place from the ComfyUI install (never copied, never modified):

| File | Path | SHA-256 | Size |
|---|---|---|---|
| `netG.pth` | `~/tools/ComfyUI/custom_nodes/comfyui_controlnet_aux/ckpts/lllyasviel/Annotators/netG.pth` | `ccabdcc3f5cf3c07cf65d58776acb21df7dfda825cdc70c9766a93fd62bfc488` | 217,631,959 bytes |

Hashed 31 Oct 2026 (file dated 10 Aug 2026). StillDrawn never recorded this hash; P47 records it here and in `NETG_SHA256`, and the job refuses to run if the file's hash differs.

```bash
shasum -a 256 ~/tools/ComfyUI/custom_nodes/comfyui_controlnet_aux/ckpts/lllyasviel/Annotators/netG.pth
~/tools/ComfyUI/.venv/bin/python seam/lines_job.py hash-netg
```

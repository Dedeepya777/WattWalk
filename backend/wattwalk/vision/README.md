# wattwalk.vision (Person 2)

How WattWalk sees: which panoramas to inspect, the image quality check, Bedrock vision calls,
the router, and fixture mode. Inventory (dedupe, coverage, corrections) is in `wattwalk/inventory/`,
the benchmark in `wattwalk/eval/`.

## Setup on a new machine

Python 3.11 or newer. From the repo root:

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install pydantic python-dotenv numpy pillow opencv-python-headless boto3 pytest
python -m pytest backend/tests -q                        # no keys needed: runs on shared/examples
```

(`backend/requirements.txt` is the full team list, including the agent and API libraries.)
Keys go in your own `.env` (never committed). Face images and audits are local only: download them
again on each machine; they are gitignored and must not be committed (decision D19).

## Run

```bash
# from backend/
python -m wattwalk.vision.cli walk --sid fixtureUnitA --reset          # fixture mode, no keys
WATTWALK_VISION_MODE=live python -m wattwalk.vision.cli inspect --sid <sid> --pano <pano>
WATTWALK_VISION_MODE=live python -m wattwalk.vision.cli walk --sid <sid> --reset --save-fixture
python -m wattwalk.eval.label_tool --sid <sid>                          # hand labels, a person only
python -m wattwalk.eval.benchmark --labels ../eval/labels.csv
# from the repo root
python -m pytest backend/tests/vision backend/tests/inventory backend/tests/eval -q
```

Live mode needs `WATTWALK_SMALL_VISION_MODEL_ID`, `WATTWALK_LARGE_VISION_MODEL_ID`, `AWS_REGION` and
AWS credentials, plus Matterport keys (through Person 1's adapter).

## Free local models for development (Ollama)

Any model id starting with `ollama/` goes to a local Ollama server instead of Bedrock:

```bash
ollama serve                      # leave running
ollama pull qwen2.5vl:7b          # about 6 GB
# in .env
WATTWALK_SMALL_VISION_MODEL_ID=ollama/qwen2.5vl:7b
WATTWALK_LARGE_VISION_MODEL_ID=ollama/qwen2.5vl:7b
```

Development only: the demo and the benchmark use Bedrock (decision D6). Measured on an M4 with
16 GB: about 20 to 25 s per detection call. Qwen2.5-VL in Ollama reports boxes in its own upsampled
grid for images under about 1000 px, so local detection images are sent at 1008 px instead of 768
(`detect.DETECT_PX_OLLAMA`); at 1008 px the measured box scale factor was 1.00.

## Thresholds (record tuned values here)

| Setting | Value | Where |
|---|---|---|
| Blur (variance of Laplacian) minimum | 60, rejects only when edge sharpness is also below 0.08 | `images.BLUR_MIN`, `images.SHARPNESS_MIN` |
| Brightness range | 40 to 220 | `images.BRIGHTNESS_MIN/MAX` |
| Detection image size | 768 px longest side | `walk.DETECT_PX` |
| Crop | 15% padding, 1024 px longest side, JPEG 90 | `images.crop` |
| Minimum box | 12 x 12 px (sent image) | `detect.MIN_BOX_PX` |
| Same-face duplicate | IoU above 0.5, keep larger | `detect.IOU_DUPLICATE` |
| One object with two labels | different labels, IoU above 0.9: keep the first reported | `detect.IOU_SAME_OBJECT` |
| Large-model cap | 5 per audit | `types.MAX_LARGE_CALLS_PER_AUDIT` |
| Consecutive Bedrock failures that fail the run | 3 | `walk.MAX_CONSECUTIVE_FAILURES` |

Tuned on real scans 2ibibwUGQAe and 2YKpZqjy5bJ (Nov 14): the original blur rule (Laplacian variance
below 60) rejected 3 of 20 sharp faces of plain walls and closet doors, wrongly marking 3 rooms partial.
Edge sharpness (mean |Laplacian| / mean gradient on edge pixels) separates them: sharp faces 0.13 to 0.34,
the same faces Gaussian-blurred 0.020 to 0.028. With the combined rule, 0 of 68 real faces are rejected
and 66 of 68 blurred copies still are (the 2 that pass are blank walls with no edges at all).

## Temporary stand-ins (remove at M2)

`deps.py` falls back when other people's modules are missing:
- `get_face_image` (Person 1): reads `audits/cache/faces/<sid>/<pano>_<face>_<res>.jpg`.
- `get_geometry` (Person 1): reads the fixture geometry files.
- `anchor_from_bbox` (Person 4): returns `(None, "none")`.
- `backend/wattwalk/store.py` (Person 3) is a minimal stand-in until the shared baseline lands.

## Real-scan results with the local model (Qwen2.5-VL 7B, Nov 14)

Full walk on 2ibibwUGQAe (1830 N Cherokee, 4 rooms, 5 views, about 6.5 minutes): every step runs
(plan, inspect, high-res, escalate, question, inventory, coverage). Boxes land on the right objects.
Accuracy is the limit: correct lamps, fan, windows, thermostat, fridge, but also false positives
(a mirror and closet doors as windows, an electrical panel as a window AC, a coffee table as a ceiling
fan). Expect Bedrock models to do better; the benchmark measures it.

Prompt tuning (Nov 14, local model, 10 Cherokee faces with "must find" and "must not find" labels
written from viewing the photos; a development check, not the hand-labeled benchmark):

| Detection prompt | Wrong detections | Missed |
|---|---|---|
| Plan E.1 wording plus one-line rules | 7 | 1 |
| Label definitions (current `DETECT_PROMPT`) | 4 | 1 |

The definitions fixed closet doors read as windows and an electrical panel read as a window AC.
Still wrong with the 7B model: a mirror as a window, a smoke detector as a ceiling light, a
mini-split as a window AC, a picture frame as a lamp. Output format, vocabulary and the "unknown"
rule are unchanged, as Appendix E requires.

Scan data: 2YKpZqjy5bJ and 1sW1YgLzUcT have no room segmentation and no walls in Matterport (no
room coverage, no anchors). 7PGYj769YXv labels every room "Other". 2ibibwUGQAe has proper labels but
no room heights. Without anchors (Person 4) dedupe can only merge one-per-room labels, so a window
seen from three panoramas is three assets until anchors land.

## Interpretations of the spec

- Fixture mode keeps the fixture's observation ids so the walk reproduces `observations.json` id for id.
- In fixture mode a high-res crop changes only the note (the example keeps `resolution: "2k"`); live mode
  switches the observation to the 4k box as plan 7.6 says.
- After an attribute correction `next_step` is left unchanged, matching `correction_response.json`.
- Coverage adds "No energy-relevant assets found" for empty reviewed rooms except hallways and similar
  corridors, which matches `coverage.json` (closet noted, hallway not).
- `router_state.json` carries extra bookkeeping fields (`final`, `inspected`, `rejected_faces`,
  `consecutive_failures`) used by `pending_observation_ids` and `coverage_inputs`.
- Observation `room_id` is the room containing the anchor when the anchor lies outside the pano's
  room (more than 0.3 m), else the pano's room (plan 7.6 says the pano's room). An object seen through
  a doorway otherwise lands in the wrong room and dedupe can never merge it. No effect until anchors exist.
- A face is rejected as blurry only when the Laplacian variance is below 60 and edge sharpness is
  below 0.08 (plan 8.2 uses the variance alone); `quality.blur` still reports the variance.
- HARD_LABELS are read from `eval/hard_labels.json`, which the benchmark writes (the `Benchmark`
  contract has no per-label field).

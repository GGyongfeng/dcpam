# DCPAM

English | [中文](README.zh.md)

DCPAM is a dual-camera point-to-axis measurement project built around a laser reference line.
The current repository mainly contains a classical computer vision workflow for geometry and precision analysis, plus a Daheng dual-camera capture utility.

## Features

- Compute the distance from a target point `P_t` to the axis defined by two measured points `P_f` and `P_b`
- Estimate measurement uncertainty with analytical error propagation
- Validate uncertainty with Monte Carlo simulation
- Visualize the 3D geometry, distance distribution, and sensitivity contribution
- Capture synchronized image pairs from two Daheng cameras for data collection

## Project Status

This repository currently ships working code for the CV-oriented analysis flow.
The README previously mentioned `MLP` and `CNN` variants, but those implementations are not present in the current tree yet.

## Installation

Clone the repository and install the Python dependencies with `uv`:

```bash
git clone https://github.com/GGyongfeng/dcpam.git
cd dcpam
uv sync
```

The dual-camera capture script also requires the Daheng Galaxy SDK and its Python binding `gxipy`.
That SDK is vendor-provided and is not installed by `uv sync`.

## Usage

Run the precision analysis script:

```bash
uv run python scripts/run_analysis.py
```

Run the Daheng dual-camera capture utility:

```bash
uv run python dual_daheng_capture.py
```

When you use the capture utility, make sure:

- Two Daheng cameras are connected
- The Daheng Galaxy SDK is installed
- `gxipy` is available from the SDK runtime

## Repository Layout

- `dcpam_cv/`: reusable CV and precision-analysis code
- `scripts/`: runnable scripts
- `pictures/`: saved capture images
- `docs/`: project notes and conventions
- `dual_daheng_capture.py`: live preview and pair capture entrypoint

## License

No license file is included in the current repository yet.

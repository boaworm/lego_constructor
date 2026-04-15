# LEGO Instructions Creator

A tool that generates LEGO building instructions from photos of assembled models.

## Overview

**Goal**: Take a folder of images showing an assembled LEGO model from different angles and automatically generate step-by-step building instructions.

**CLI Usage**:
```bash
./generate_lego_instructions path/to/folder/with/images
```

---

## Tech Stack

### Core Technologies

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Language** | Python 3.13+ | Best ecosystem for CV, image processing, and AI APIs; latest stable with full library support |
| **Vision API** | Claude Vision API | Strong image understanding, can identify LEGO bricks and spatial relationships |
| **Image Processing** | OpenCV / Pillow | Local image preprocessing, resizing, format handling |
| **3D Modeling** | Open3D or Trimesh | Reconstructing 3D structure from detected bricks |
| **Output Generation** | Jinja2 + HTML/PDF | Templating for instruction generation |
| **CLI Framework** | Click or argparse | Simple, robust command-line interface |

### Supporting Libraries
- **numpy/scipy** — Spatial calculations, matrix operations
- **dataclasses** — Type-safe brick/component definitions
- **json** — Configuration and data serialization
- **pytest** — Testing

---

## Architecture

### High-Level Flow

```
Input Images
    ↓
[Image Preprocessing] → Standardize formats, sizes, orientations
    ↓
[Brick Detection] → Claude Vision API analyzes each image
    ↓
[3D Reconstruction] → Merge multi-view detections into 3D model
    ↓
[Assembly Sequencing] → Determine optimal build order
    ↓
[Instruction Generation] → Create formatted output (HTML/PDF)
    ↓
Output Instructions
```

### Core Components

#### 1. **Image Processor** (`image_processor.py`)
- Load images from input folder
- Validate image quality
- Normalize sizes/formats
- Detect image angles/perspectives

#### 2. **Brick Detector** (`brick_detector.py`)
- Use Claude Vision API to analyze each image
- Extract: brick type, color, position hints, orientation
- Return structured brick data per image

#### 3. **3D Reconstructor** (`reconstructor_3d.py`)
- Merge multi-view brick detections
- Resolve conflicts/inconsistencies across views
- Build 3D coordinate system
- Assign precise (x, y, z) positions to each brick

#### 4. **Assembly Sequencer** (`sequencer.py`)
- Determine build dependencies (which bricks must come before others)
- Generate logical assembly order (bottom-up, structural stability)
- Group bricks into "steps"

#### 5. **Instruction Generator** (`instruction_generator.py`)
- Create visual instructions for each step
- Generate HTML or PDF output
- Include: parts list, step visuals, part counts per step

#### 6. **Data Models** (`models.py`)
```python
@dataclass
class Brick:
    type: str              # e.g., "2x4 stud brick"
    color: str             # e.g., "red", "blue"
    position: tuple(x, y, z)  # 3D coordinates
    orientation: tuple     # Rotation angles
    source_image: str      # Which image(s) detected this

@dataclass
class BuildStep:
    step_number: int
    bricks_to_add: List[Brick]
    instructions_text: str
    visualization: Image
```

---

## Data Flow

1. **Input** → Folder of JPG/PNG images
2. **Detection Phase** → For each image, Claude Vision extracts brick locations
3. **Integration Phase** → Correlate bricks across multiple viewpoints
4. **Validation** → Check for consistency, resolve contradictions
5. **Assembly Logic** → Determine sequential order
6. **Output** → Formatted instructions (HTML/PDF with visuals)

---

## Key Challenges & Approaches

### Challenge 1: Brick Detection Accuracy
- **Problem**: Partial visibility, shadows, overlapping bricks
- **Approach**:
  - Use multiple angles to improve confidence
  - Fallback to manual correction UI (future enhancement)
  - Leverage Claude Vision's spatial reasoning

### Challenge 2: 3D Position Estimation
- **Problem**: Converting 2D image coordinates to 3D space
- **Approach**:
  - Use camera calibration if EXIF data available
  - Apply perspective geometry assumptions
  - Cross-validate across multiple viewpoints
  - Use known LEGO brick dimensions as anchors

### Challenge 3: Assembly Sequencing
- **Problem**: Determining optimal build order
- **Approach**:
  - Bottom-up layer approach (gravity-based)
  - Structural dependency analysis
  - Minimize overhang/instability
  - Heuristic: prioritize supporting structure first

### Challenge 4: Handling Edge Cases
- **Problem**: Unclear angles, poor lighting, complex overlaps
- **Approach**:
  - Image quality validation with user warnings
  - Confidence scoring on detections
  - User-guided correction workflow (MVP+ feature)

---

## MVP Scope (Phase 1)

### In Scope
- ✅ CLI interface: `./generate_lego_instructions <folder>`
- ✅ Multi-image input support (JPG, PNG)
- ✅ Brick detection via Claude Vision API
- ✅ Basic 3D reconstruction (assuming orthogonal views)
- ✅ Simple assembly sequencing (layer-based)
- ✅ HTML instruction output with parts list

### Out of Scope (for MVP)
- ❌ PDF generation (use browser print instead)
- ❌ Interactive 3D viewer
- ❌ Manual correction UI
- ❌ Support for non-standard LEGO shapes
- ❌ Automatic photo angle detection

---

## Project Structure

```
lego_constructor/
├── generate_lego_instructions       # Main CLI script
├── lego_creator/
│   ├── __init__.py
│   ├── models.py                    # Data models (Brick, BuildStep, etc.)
│   ├── image_processor.py           # Load & preprocess images
│   ├── brick_detector.py            # Claude Vision integration
│   ├── reconstructor_3d.py          # 3D reconstruction logic
│   ├── sequencer.py                 # Assembly order logic
│   ├── instruction_generator.py     # Output generation
│   └── config.py                    # Constants, paths, config
├── tests/
│   ├── test_brick_detector.py
│   ├── test_reconstructor.py
│   └── test_sequencer.py
├── example/                         # Example project output
│   ├── 1000x800.jpg                 # Input image
│   └── output/                      # Generated instructions
│       ├── instructions.html        # Full instruction set
│       └── step_01.png - step_08.png
├── mini_castle/                     # Example: multi-image model
│   ├── *.png                        # Multiple reference images
│   └── output/                      # Generated instructions
├── nano_castle/                     # Example: single image model
│   ├── 1000x800.jpg                 # Input image
│   └── output/                      # Generated instructions
├── alamo/                           # Example: building reference
│   └── images/                      # Reference photos
├── requirements.txt
├── README.md
└── LegoInstructionsCreator.md        # This file
```

---

## Development Phases

### Phase 1: MVP
- [ ] Set up CLI & project structure
- [ ] Image loading & validation
- [ ] Basic Claude Vision brick detection
- [ ] Simple 3D reconstruction (layer-based)
- [ ] Basic instruction generator (HTML)
- [ ] Test with sample model

### Phase 2: Refinements
- [ ] Improved 3D reconstruction with perspective
- [ ] Smarter assembly sequencing
- [ ] Better instruction formatting & visuals
- [ ] Error handling & user feedback

### Phase 3: Polish
- [ ] PDF export
- [ ] Performance optimization
- [ ] User documentation
- [ ] Example models & outputs

---

## Dependencies & Setup

**Requirements**: Python 3.13+

```bash
# Create virtual environment
python3.13 -m venv venv
source venv/bin/activate

# Install dependencies
pip install anthropic opencv-python pillow numpy open3d jinja2 click pytest
```

---

## Success Criteria

- Tool successfully processes a folder of 3-5 images
- Generates a readable HTML instruction set
- Parts list is accurate
- Assembly order is logical and buildable
- No manual corrections needed for simple models

---

## Examples & Current Status

The project includes several example models that demonstrate the current capabilities:

### Example Models

| Model | Status | Details |
|-------|--------|---------|
| **example/** | ✅ Complete | Single image → 8 step instructions. Basic model showcasing full pipeline. |
| **nano_castle/** | ✅ Complete | Single 1000x800px image → 8 step instructions with parts list. |
| **mini_castle/** | ✅ Complete | Multi-image input (3 PNG reference photos) → 10 step instructions. |
| **alamo/** | 🔄 In Progress | Building reference images for complex model testing. |

### How to Run

Generate instructions for any example:

```bash
# Single image example
./generate_lego_instructions example

# Multi-image example
./generate_lego_instructions mini_castle

# View results
open example/output/instructions.html
open nano_castle/output/instructions.html
open mini_castle/output/instructions.html
```

### Output Features

Each generated instruction set includes:

- **Header with Reference Image** — Shows the expected final result
- **Parts List** — Complete BOM with color and quantity per brick type
- **Step-by-Step Visuals** — Top-down grid view for each assembly step
- **New Brick Highlighting** — Yellow borders highlight newly added pieces in each step
- **Layer Information** — Shows construction layer/height for each step
- **Responsive HTML** — Works on desktop and mobile browsers

---

## Current Project Status

### ✅ Completed Features
- [x] CLI interface with Click
- [x] Multi-format image loading (JPG, PNG)
- [x] Claude Vision API brick detection
- [x] 3D reconstruction with position tracking
- [x] Layer-based assembly sequencing
- [x] HTML instruction generation with embedded visuals
- [x] Parts list generation with color coding
- [x] Reference image in instruction headers
- [x] Responsive design for instruction display

### 🔄 In Progress / Testing
- [ ] Multi-image example models
- [ ] Edge case handling (poor lighting, overlaps)
- [ ] Confidence scoring for detections

### 📋 Next Steps
- [ ] PDF export capability
- [ ] Improved 3D visualization
- [ ] Performance optimization for large models
- [ ] Enhanced error messages and user guidance

---

## Future Enhancements

1. **Interactive Web UI** — Web interface for upload & viewing
2. **Real-time Feedback** — Confidence scores for each detection
3. **Manual Annotation Tool** — Correct detection errors interactively
4. **Video Input** — Generate instructions from video feeds
5. **Parts Marketplace** — Link to suppliers for part purchasing
6. **AR Visualization** — Mobile AR app for instructions


# MockVox CLI User Guide

## Overview

MockVox is a voice synthesis & cloning toolkit supporting three core operations: audio upload, model training, and voice generation. This document details command syntax, parameter configurations, and usage examples.

---

## System Requirements

- MeCab library installed (for linguistic feature processing)
- Python 3.11+ runtime
- Valid API credentials (for cloud services)

---

## Usage Workflow

```mermaid
graph TD
    A[Upload Audio File] -.-> |Optional| B[ASR Revision]
    A --> C[Model Training]
    B -.-> C
    A -.-> |Optional| E[Add Audio]
    E -.-> C
    C --> D[Inference]
    C -.-> |Optional| G[Resume Training]
    G -.-> D
```

---

## Command Reference

### 1. 🚀 Upload Voice Sample

```bash
mockvox upload [OPTIONS] FILE_PATH
```

**Function**: Preprocess raw audio files

| Parameter            | Description                          | Default | Required |
|----------------------|--------------------------------------|---------|----------|
| `FILE_PATH`          | Absolute path to audio file          | -       | Yes      |
| `--no-denoise`       | Disable automatic denoising          | Enabled | No       |
| `--language LANG`    | Language code (zh/can/en/ja/ko)       | zh      | No       |

**Example**:

```bash
mockvox upload /data/sample.wav --language zh 
```

Returns a file ID {fileID}.  

Automatic Speech Recognition (ASR) results are saved in `./data/asr/{fileID}/output.json`. Edit this file for ASR correction.

Audio slices are stored in `./data/sliced/{fileID}`. Denoised files are saved in `./data/denoised/{fileID}`.

---

### 2. ➕ Add Audio Samples to Existing Dataset

```bash
mockvox add fileID file_path
```

**Function**: add new audio files to existing uploaded samples

| Parameter            | Description                          | Default | Required |
|----------------------|--------------------------------------|---------|----------|
| `fileID`          | File ID returned by upload command          | -       | Yes      |
| `FILE_PATH`       | Absolute path to new audio file          | - | Yes       |

**Example**:

```bash
mockvox add "20250522095117519601.e6abd9db" /data/additional.wav
```

1. Adds new audio to specified fileID's dataset
2. Automatically performs same preprocessing as initial upload
3. ASR results incrementally update original directory: ./data/asr/{fileID}/output.json
4. Voice segmentation/denoising outputs stored in original fileID's directory
5. All data linked using original fileID

---

### 3. 🧠 Train Voice Model

```bash
mockvox train [OPTIONS] FILE_ID # File ID from upload response
```

**Function**: Train custom voice model using uploaded samples

| Parameter              | Description                          | Default | Required |
|------------------------|--------------------------------------|---------|----------|
| `FILE_ID`              | Identifier from upload operation     | -       | Yes      |
| `--epochs_sovits EPOCH`| Training epochs for SoVITS model     | 1      | No       |
| `--epochs_gpt EPOCH`   | Training epochs for GPT model        | 1      | No       |
| `--version`            | Model version (v2/v4)                | v4     | No       |
| `--no-denoise`         | Use non-denoised audio               | Denoised| No       |

**Example**:

```bash
mockvox train "20250522095117519601.e6abd9db.896806622ccb47a9ac1ee1669daf1938" --epochs_sovits 2 --epochs_gpt 2
```

---

### 4. 🔊 Generate Synthetic Speech

```bash
mockvox inference [OPTIONS] MODEL_ID REF_AUDIO PROMPT_TEXT TARGET_TEXT
```

**Function**: Synthesize target speech using trained model

| Parameter             | Description                          | Default | Required |
|-----------------------|--------------------------------------|---------|----------|
| `MODEL_ID`            | Model ID from training               | -       | Yes      |
| `REF_AUDIO`           | Absolute path to reference audio     | -       | Yes      |
| `PROMPT_TEXT`         | Text corresponding to reference audio| -       | Yes      |
| `TARGET_TEXT`         | Text to synthesize                   | -       | Yes      |
| `--promptLanguage LANG`| Language of reference audio (zh/can/en/ja/ko) | zh | No |
| `--targetLanguage LANG`| Target text language code            | zh  | No       |
| `--top_p` | Top-p sampling | 1 | No |
| `--top_k` | Top-k sampling | 15 | No |
| `--temperature` | Sampling temperature | 1 | No |
| `--speed` | Speech speed | 1 | No |

**Target Language Codes**:

| Language Code | Description                          |
|---------------|--------------------------------------|
| all_zh        | Full Chinese                         |
| all_can       | Full Cantonese                       |
| en            | Full English                         |
| all_ja        | Full Japanese                        |
| all_ko        | Full Korean                          |
| zh            | Chinese-English mixed                |
| ja            | Japanese-English mixed               |
| can           | Cantonese-English mixed              |
| ko            | Korean-English mixed                 |
| auto          | Auto-detect multiple languages (excl. Cantonese) |
| auto_can      | Auto-detect with Cantonese support   |

**Example**:

```bash
mockvox inference "20250522095117519601.e6abd9db.896806622ccb47a9ac1ee1669daf1938" /ref/reference.wav "Happy birthday" "Let's celebrate!"
```

The inference results are saved in the ./data/output directory.

---

### 5. ⏯ Resume Model Training

```bash
mockvox resume [options] ModelID
```

**Function**​​: Resume model training from existing checkpoints

| Parameter             | Description                          | Default | Required |
|-----------------------|--------------------------------------|---------|----------|
| `MODEL_ID`            | Model ID from training               | -       | Yes      |
| `--epochs_sovits EPOCH`| Training epochs for SoVITS model     | 2      | No       |
| `--epochs_gpt EPOCH`   | Training epochs for GPT model        | 2      | No       |

**​​Example**​​:

```bash
mockvox resume 20250524182510033061.370358d9.af07654e5ffe46c788448c05a0dedca3 --epochs_sovits 3 --epochs_gpt 5
```

**Implementation Details**​​:

1. Automatically loads the latest checkpoint from ./data/weights/{ModelID} directory
2. New training results will overwrite existing model files

### 6. ℹ️ View Model Information

```bash
mockvox info ModelID
```

**Function**​​: Display model training metadata

| Parameter             | Description                          | Default | Required |
|-----------------------|--------------------------------------|---------|----------|
| `MODEL_ID`            | Model ID from training               | -       | Yes      |

## Key Features

- **Version Control**: Maintain compatibility via `--version` parameter
- **Smart Denoising**: Enabled by default (disable with `--no-denoise`)
- **Multilingual Support**: Chinese/Cantonese/English/Japanese/Korean
- **Workflow Enforcement**: Strict operation sequence (Upload → Revision[Optional] → Train → Synthesize)

---

## Troubleshooting

❗ For `MeCab not found` error:

```bash
Debian/Ubuntu systems
sudo apt-get install mecab libmecab-dev mecab-ipadic
```

❗ Always use absolute paths to avoid file resolution errors

❗ Training epochs >30 may cause overfitting with small datasets

---
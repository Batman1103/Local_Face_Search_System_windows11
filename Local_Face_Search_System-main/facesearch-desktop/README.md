# FaceSearch Desktop

A Windows-first, local-only desktop application for searching a user's own photo library by face. There is **no webcam/live-camera feature**.

## User workflow

1. Install and open FaceSearch.
2. Select the folder containing the photos to search.
3. FaceSearch scans the folder in the background, recursively.
4. It stores compact face vectors and file metadata only; original photographs are never copied.
5. A background filesystem watcher indexes newly created or changed images and marks deleted images inactive. A periodic reconciliation scan catches missed events on removable/network drives.
6. Select a reference photograph containing the face to search for.
7. Review matches, open the original photograph, or reveal it in File Explorer.

The first scan can take time on a large library. Subsequent launches reuse the index and process only new or changed files. Keep the selected drive connected for automatic monitoring.

## Compact index

Each detected face is represented by a normalized 512-dimensional ArcFace embedding, quantized to signed 8-bit values. The raw vector uses **512 bytes per face** (rather than 2,048 bytes for float32), plus SQLite metadata and filesystem overhead.

Examples of raw vector payload only:

| Indexed faces | Approximate vector payload |
|---:|---:|
| 10,000 | 4.9 MiB |
| 100,000 | 48.8 MiB |
| 500,000 | 244 MiB |
| 1,000,000 | 488 MiB |

The search performs a bounded, batched cosine-similarity scan over active vectors; it does not load the complete collection into RAM. INT8 quantization is a storage/throughput trade-off and can slightly change ranking near the similarity threshold. Similarity scores are retrieval scores, not identity probabilities.

The application generates small previews on demand. It does not maintain a second copy of the original photo library or permanently cache thumbnails.

## Data locations

The index and database are kept outside the photo folders.

Windows:
```text
%LOCALAPPDATA%\FaceSearch\
├── index\faces.int8
└── metadata.db
```

Linux development:
```text
~/.local/share/facesearch/
├── index/faces.int8
└── metadata.db
```

## Windows development

Recommended build machine: Windows 10/11 x64, Python 3.11, Node.js LTS and npm.

From PowerShell in this directory:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\build-windows.ps1
```

The script installs backend dependencies, creates a PyInstaller backend bundle, builds the React UI and creates an NSIS installer. The installer output is placed in `desktop\dist`.

For frontend/backend development, create `.venv` and install `backend\requirements.txt`, then build the renderer and run Electron:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend
npm ci
npm run build
cd ..\desktop
npm ci
npm start
```

## First launch and model files

InsightFace's `buffalo_l` pretrained model is downloaded on first launch into the user's local model cache. Therefore the first launch needs internet access; subsequent recognition is local. Model weights are not copied into the installer. Check the model's license and usage terms before commercial distribution.

## Architecture

```text
Electron + React desktop
        |
        | localhost only (127.0.0.1:8765)
        v
FastAPI local backend
        ├── InsightFace / ONNX Runtime (CPU)
        ├── INT8 compact vector file (512 bytes / face)
        ├── SQLite image/face metadata
        └── Watchdog recursive folder monitor
                    |
                    v
            User-selected photo folder
```

## Operational notes

- Select one root folder per collection. Subfolders are scanned recursively.
- Do not select the entire system drive; choose only the photo folders you want indexed.
- Keep external drives mounted and their drive letters stable while searching. The app stays active in the system tray when its window is closed; if you fully quit it, monitoring pauses and resumes/reconciles the folder the next time you launch it.
- The initial scan is CPU intensive and can take hours for a very large library.
- If the selected folder is unavailable, the index remains on disk; reconnect the same folder or rescan.
- Deleted/changed faces are deactivated in metadata; the append-only vector file may retain old inactive bytes. Use the rebuild endpoint after substantial churn to compact the vector file; rebuilding requires reprocessing the library.
- The backend listens only on loopback and is not intended to be exposed to a network.
- Use face search only with photographs and identities you are authorized to process. Protect the local index because embeddings are biometric data.

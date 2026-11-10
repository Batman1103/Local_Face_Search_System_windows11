from pathlib import Path
import cv2
import numpy as np
from insightface.app import FaceAnalysis

class FaceEngine:
    def __init__(self, model_name="buffalo_l", providers=None):
        self.app = FaceAnalysis(name=model_name, providers=providers or ["CPUExecutionProvider"])
        self.app.prepare(ctx_id=0, det_size=(640, 640))

    def read_image(self, source):
        if isinstance(source, (str, Path)):
            img = cv2.imread(str(source))
        else:
            img = cv2.imdecode(np.frombuffer(source, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image")
        return img

    def detect(self, img):
        results = []
        original_h, original_w = img.shape[:2]
        max_side = max(original_h, original_w)
        scale = min(1.0, 1600.0 / max_side)
        working = img
        if scale < 1.0:
            working = cv2.resize(
                img,
                (max(1, int(original_w * scale)), max(1, int(original_h * scale))),
                interpolation=cv2.INTER_AREA
            )
        for face in self.app.get(working):
            emb = np.asarray(face.embedding, dtype="float32")
            norm = np.linalg.norm(emb)
            if norm == 0:
                continue
            bbox = [int(round(float(v) / scale)) for v in face.bbox]
            results.append({
                "embedding": emb / norm,
                "bbox": bbox,
                "score": float(face.det_score)
            })
        return results

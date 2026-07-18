import cv2
import os
import numpy as np


class VisionEngine:
    """
    Face recognition using OpenCV LBPH.

    Dataset folder structure:
      – multiple images per person (subfolder = email):
          dataset/
            ion@student.ro/
              1.jpg
              2.jpg
              3.jpg
            ana@student.ro/
              1.jpg
    """

    # Am modificat pragul de la 80 la 130.
    # 80 este prea strict cand exista o singura poza in dataset.
    CONFIDENCE_THRESHOLD = 140

    def __init__(self, dataset_path="dataset"):
        self.dataset_path = dataset_path
        self.label_dict   = {}
        self.is_trained   = False
        self._skip        = 0

        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        self.recognizer = cv2.face.LBPHFaceRecognizer_create(
            radius=2, neighbors=8, grid_x=8, grid_y=8
        )
        self._train()

    # Training
    def _train(self):
        print("[VISION] Loading dataset...")

        if not os.path.exists(self.dataset_path):
            os.makedirs(self.dataset_path)
            print(f"[VISION] Created '{self.dataset_path}/' — add photos!")
            return

        faces, labels, current_id = [], [], 0

        # Option B: subfolders
        subdirs = [d for d in os.listdir(self.dataset_path)
                   if os.path.isdir(os.path.join(self.dataset_path, d))]

        if subdirs:
            for folder in sorted(subdirs):
                email    = folder
                folder_p = os.path.join(self.dataset_path, folder)
                count    = 0
                for fname in os.listdir(folder_p):
                    if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
                        continue
                    rois = self._extract_faces(os.path.join(folder_p, fname))
                    for roi in rois:
                        faces.append(roi)
                        labels.append(current_id)
                        count += 1
                if count > 0:
                    self.label_dict[current_id] = email
                    current_id += 1
                    print(f"[VISION] {email}: {count} face(s) loaded")
                else:
                    print(f"[VISION] WARNING — no faces found in folder '{folder}'")

        else:
            # Option A: flat files
            for fname in sorted(os.listdir(self.dataset_path)):
                if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
                    continue
                email = os.path.splitext(fname)[0]
                rois  = self._extract_faces(os.path.join(self.dataset_path, fname))
                if rois:
                    for roi in rois:
                        faces.append(roi)
                        labels.append(current_id)
                    self.label_dict[current_id] = email
                    current_id += 1
                    print(f"[VISION] {email}: {len(rois)} face(s) loaded")
                else:
                    print(f"[VISION] WARNING — no face detected in '{fname}'")
                    print(f"         Tip: use a clear, front-facing photo in good light.")

        if faces:
            self.recognizer.train(faces, np.array(labels))
            self.is_trained = True
            print(f"[VISION] Model trained on {len(self.label_dict)} person(s), "
                  f"{len(faces)} face image(s) total.")
        else:
            print("[VISION] No training data — recognition disabled.")

    def _extract_faces(self, img_path):
        img = cv2.imread(img_path)
        if img is None:
            return []

        # Try multiple scales to find the face
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        rois = []
        for scale in [1.05, 1.1, 1.2]:
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=scale, minNeighbors=3, minSize=(50, 50)
            )
            if len(faces) > 0:
                for (x, y, w, h) in faces:
                    roi = cv2.resize(gray[y:y+h, x:x+w], (100, 100))
                    rois.append(roi)
                break   # stop at first successful scale

        return rois

    # Frame processing
    def process_frame(self, frame):
        detected_emails = []

        # Process every frame (removed skip for better responsiveness)
        try:
            gray   = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray_e = cv2.equalizeHist(gray)

            faces = self.face_cascade.detectMultiScale(
                gray_e, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80)
            )

            for (x, y, w, h) in faces:
                email      = "Necunoscut"
                color      = (60, 60, 220)
                confidence = 999

                if self.is_trained:
                    roi   = cv2.resize(gray_e[y:y+h, x:x+w], (100, 100))
                    label_id, confidence = self.recognizer.predict(roi)
                    if confidence < self.CONFIDENCE_THRESHOLD:
                        email = self.label_dict.get(label_id, "Necunoscut")
                        color = (0, 210, 100)

                detected_emails.append(email)

                # Bounding box
                cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
                cv2.rectangle(frame, (x, y-36), (x+w, y), color, cv2.FILLED)

                display = email.split("@")[0] if email != "Necunoscut" else "UNKNOWN"

                cv2.putText(frame, display,
                            (x+6, y-8), cv2.FONT_HERSHEY_DUPLEX,
                            0.55, (255, 255, 255), 1, cv2.LINE_AA)

        except Exception as e:
            print(f"[VISION] Error in process_frame: {e}")

        return frame, detected_emails
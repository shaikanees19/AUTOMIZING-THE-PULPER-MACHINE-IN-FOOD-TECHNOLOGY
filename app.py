from flask import Flask, render_template, request, Response, jsonify
from ultralytics import YOLO
import os
import cv2
import requests
import time
import threading

app = Flask(__name__)

# Load YOLO model
model = YOLO("best.pt")

# ESP32 IP address
ESP32_IP = "http://10.224.14.126/data"

# Class → Grade mapping
class_map = {
    "Ripe": "Grade 1",
    "spotted ripe": "Grade 1",
    "semi-ripe": "Grade 2",
    "unripe": "Grade 3",
    "spotted unripe": "Grade 2",
    "rotten": "Grade 3"
}

# Grade → RPM mapping
rpm_map = {
    "Grade 1": "40",
    "Grade 2": "60",
    "Grade 3": "80"
}

UPLOAD_FOLDER = "static/uploads"
RESULT_FOLDER = "static/results"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)

# Shared state for real-time detection
rt_state = {
    "detected_class": "—",
    "grade": "—",
    "rpm": "—",
    "confidence": 0,
    "esp32_status": ""
}
rt_lock = threading.Lock()
last_sent_time = 0
last_sent_class = None


def send_to_esp32(detected_class, rpm):
    try:
        params = {"class": detected_class, "rpm": rpm}
        resp = requests.get(ESP32_IP, params=params, timeout=2)
        print(f"Sent to ESP32: {params} → {resp.status_code}")
        return "✅ Sent to ESP32"
    except requests.exceptions.ConnectionError:
        return "⚠️ ESP32 not reachable"
    except requests.exceptions.Timeout:
        return "⚠️ ESP32 timed out"
    except Exception as e:
        return f"⚠️ {e}"


# ── FILE UPLOAD ROUTE ──
@app.route("/", methods=["GET", "POST"])
def index():
    grade = None
    rpm = None
    image_path = None
    detected_class = None
    esp32_status = None

    if request.method == "POST":
        file = request.files.get("image")
        if file:
            upload_path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(upload_path)

            results = model(upload_path)
            annotated_frame = results[0].plot()

            result_path = os.path.join(RESULT_FOLDER, file.filename)
            cv2.imwrite(result_path, annotated_frame)
            image_path = result_path

            if len(results[0].boxes) > 0:
                cls_id = int(results[0].boxes.cls[0])
                detected_class = model.names[cls_id]
                grade = class_map.get(detected_class, "Unknown")
                rpm = rpm_map.get(grade, "0")
                esp32_status = send_to_esp32(detected_class, rpm)
            else:
                detected_class = "No tomato detected"
                grade = "N/A"
                rpm = "0"

    return render_template(
        "index.html",
        grade=grade, rpm=rpm,
        image_path=image_path,
        detected_class=detected_class,
        esp32_status=esp32_status
    )


# ── REAL-TIME WEBCAM STREAM ──
def generate_frames():
    global last_sent_time, last_sent_class
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = model(frame, conf=0.25)
        annotated = results[0].plot()

        if len(results[0].boxes) > 0:
            boxes = results[0].boxes
            best_idx = boxes.conf.argmax().item()
            cls_id = int(boxes.cls[best_idx])
            detected_class = model.names[cls_id]
            confidence = float(boxes.conf[best_idx])
            grade = class_map.get(detected_class, "Unknown")
            rpm = rpm_map.get(grade, "0")

            cv2.putText(annotated, f"Grade: {grade}", (10, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (30, 160, 110), 2)
            cv2.putText(annotated, f"RPM: {rpm}", (10, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (220, 159, 48), 2)
            cv2.putText(annotated, f"Conf: {confidence:.0%}", (10, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

            now = time.time()
            if detected_class != last_sent_class or (now - last_sent_time) >= 3:
                status = send_to_esp32(detected_class, rpm)
                last_sent_time = now
                last_sent_class = detected_class
                with rt_lock:
                    rt_state.update({
                        "detected_class": detected_class,
                        "grade": grade,
                        "rpm": rpm,
                        "confidence": round(confidence * 100),
                        "esp32_status": status
                    })
        else:
            with rt_lock:
                rt_state.update({
                    "detected_class": "No tomato",
                    "grade": "—", "rpm": "—",
                    "confidence": 0, "esp32_status": ""
                })

        _, buffer = cv2.imencode(".jpg", annotated)
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")

    cap.release()


@app.route("/video_feed")
def video_feed():
    return Response(generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/rt_status")
def rt_status():
    with rt_lock:
        return jsonify(rt_state)


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
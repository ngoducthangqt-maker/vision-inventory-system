"""vision-service: YOLO11 + OpenCV carton counting service.

Receives an RTSP stream or a video file, counts unique carton boxes using
YOLO11 object tracking, and reports the running count to the
``inventory-service`` via its REST API (``restock`` / ``consume`` endpoints).
"""

__version__ = "1.0.0"

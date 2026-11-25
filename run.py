"""Chạy ứng dụng: python run.py   (hoặc: flask --app run run --debug)

Muốn quét QR bằng camera điện thoại trong mạng LAN (cần HTTPS):
    pip install pyopenssl
    set HTTPS=1   (macOS/Linux: export HTTPS=1)
    python run.py      -> mở https://<IP-máy-tính>:5000 trên điện thoại, chấp nhận cảnh báo chứng chỉ
"""
import os

from clubhub import create_app

app = create_app()

if __name__ == "__main__":
    ssl = None
    if os.environ.get("HTTPS") == "1":
        try:
            import OpenSSL  # noqa: F401
            ssl = "adhoc"
        except ImportError:
            print("Cần cài 'pyopenssl' để bật HTTPS: pip install pyopenssl  -> đang chạy HTTP.")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG", "1") == "1", ssl_context=ssl)

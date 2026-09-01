"""启动脚本"""
import socket

import uvicorn


def port_is_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) == 0


if __name__ == "__main__":
    if port_is_in_use(8080):
        raise SystemExit(
            "[ERROR] HTTP port 8080 is already in use. "
            "The backend may already be running: http://127.0.0.1:8080/docs"
        )
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=False)

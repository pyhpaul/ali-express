"""Simple proxy monitor - run alongside scrape"""

import socket
import subprocess
import time
import sys


def check():
    ports = []
    for port in range(11081, 11085):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    s.send(b"\x05\x01\x00")
                    resp = s.recv(2)
                    status = "SOCKS5" if resp == b"\x05\x00" else "OPEN"
                    ports.append((port, status))
        except Exception:
            pass

    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq xray.exe"],
        capture_output=True, text=True, encoding="gbk", errors="ignore"
    )
    xray_count = result.stdout.count("xray.exe")

    return ports, xray_count


def main():
    print("Monitoring proxy ports (Ctrl+C to stop)...")
    print("-" * 40)

    while True:
        try:
            ports, xray_count = check()
            ts = time.strftime("%H:%M:%S")

            if ports:
                port_str = ", ".join(f"{p[0]}({p[1]})" for p in ports)
                print(f"[{ts}] xray={xray_count} ports={port_str}")
            else:
                print(f"[{ts}] xray={xray_count} ports=none")

            time.sleep(2)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()

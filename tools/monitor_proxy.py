"""Real-time v2rayN proxy connection monitor"""

import subprocess
import time
import socket
import sys


def check_xray_processes():
    """Check xray process count"""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq xray.exe", "/FO", "CSV"],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="ignore"
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) > 1:
            return len(lines) - 1
    except Exception:
        pass
    return 0


def check_port_listening(port):
    """Check if port is listening"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            result = s.connect_ex(("127.0.0.1", port))
            return result == 0
    except Exception:
        return False


def check_proxy_connection(port):
    """Test proxy connection via SOCKS5 handshake"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return False, "not listening"

            s.send(b"\x05\x01\x00")
            response = s.recv(2)
            if response == b"\x05\x00":
                return True, "SOCKS5 ready"
            else:
                return False, f"handshake failed: {response.hex()}"
    except Exception as e:
        return False, str(e)


def get_active_connections():
    """Get active proxy connections"""
    try:
        result = subprocess.run(
            ["netstat", "-an"],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="ignore"
        )
        proxy_connections = []
        for line in result.stdout.split("\n"):
            if "1108" in line and "ESTABLISHED" in line:
                proxy_connections.append(line.strip())
        return proxy_connections
    except Exception:
        return []


def monitor_loop(interval=2):
    """Main monitor loop"""
    print("=" * 50)
    print("v2rayN Proxy Monitor")
    print("=" * 50)
    print(f"Interval: {interval}s")
    print("Press Ctrl+C to stop")
    print("=" * 50)

    while True:
        try:
            if sys.platform == "win32":
                subprocess.run(["cls"], shell=True)
            else:
                subprocess.run(["clear"])

            print("=" * 50)
            print(f"v2rayN Proxy Monitor - {time.strftime('%H:%M:%S')}")
            print("=" * 50)

            xray_count = check_xray_processes()
            print(f"\n[Process]")
            print(f"  xray count: {xray_count}")

            print(f"\n[Proxy Ports]")
            active_ports = []
            for port in range(11081, 11085):
                is_listening = check_port_listening(port)
                status = "LISTENING" if is_listening else "OFF"
                print(f"  Port {port}: {status}")
                if is_listening:
                    active_ports.append(port)

            print(f"\n[Connection Test]")
            for port in active_ports:
                is_ready, message = check_proxy_connection(port)
                status = "[OK]" if is_ready else "[FAIL]"
                print(f"  Port {port}: {status} {message}")

            connections = get_active_connections()
            print(f"\n[Active Connections]")
            print(f"  Proxy connections: {len(connections)}")
            if connections:
                print("  Recent:")
                for conn in connections[:3]:
                    print(f"    {conn}")

            print("\n" + "=" * 50)
            print("Browser uses these ports during scrape")
            print("=" * 50)

            time.sleep(interval)

        except KeyboardInterrupt:
            print("\n\nMonitor stopped")
            break
        except Exception as e:
            print(f"\nError: {e}")
            time.sleep(interval)


if __name__ == "__main__":
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    monitor_loop(interval)

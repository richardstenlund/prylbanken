"""Opt-in public HTTP checks with pinned DNS, bounded redirects and no credentials."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import http.client
import ipaddress
import io
import socket
import ssl
import threading
import time
from urllib.parse import urljoin, urlsplit

DNS_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="link-dns")
DNS_SLOTS = threading.BoundedSemaphore(2)


def public_address(value):
    address = ipaddress.ip_address(value)
    return (address.is_global and str(address) not in {"168.63.129.16", "192.0.0.9", "192.0.0.10"} and
            not address.is_multicast and not address.is_reserved and
            not (isinstance(address, ipaddress.IPv6Address) and
                 (address.ipv4_mapped or address.sixtofour or address.teredo)))


class DeadlineReader(io.RawIOBase):
    def __init__(self, sock, deadline):
        self.sock, self.deadline = sock, deadline

    def readable(self):
        return True

    def readinto(self, buffer):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Link deadline exceeded")
        self.sock.settimeout(remaining)
        return self.sock.recv_into(buffer)


class DeadlineSocket:
    def __init__(self, sock, deadline):
        self.sock, self.deadline = sock, deadline

    def makefile(self, mode):
        return io.BufferedReader(DeadlineReader(self.sock, self.deadline))

    def sendall(self, data):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Link deadline exceeded")
        self.sock.settimeout(remaining)
        self.sock.sendall(data)

    def close(self):
        self.sock.close()


def endpoint(url, deadline):
    if len(url) > 2000 or any(ord(c) < 33 for c in url) or "\\" in url:
        raise ValueError("Länken får inte innehålla blanksteg, kontrolltecken eller omvända snedstreck.")
    parsed = urlsplit(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Endast HTTP/HTTPS utan inloggningsuppgifter stöds.")
    host = parsed.hostname.encode("idna").decode()
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in (80, 443):
        raise ValueError("Länkkontroll tillåter bara port 80 och 443.")
    if not DNS_SLOTS.acquire(blocking=False):
        raise ValueError("DNS-kontrollen är upptagen. Försök igen senare.")
    try:
        future = DNS_POOL.submit(socket.getaddrinfo, host, port, 0, socket.SOCK_STREAM)
    except RuntimeError:
        DNS_SLOTS.release()
        raise
    future.add_done_callback(lambda _: DNS_SLOTS.release())
    try:
        addresses = future.result(timeout=max(.01, min(3, deadline - time.monotonic())))
    except FutureTimeout:
        raise ValueError("DNS-kontrollen tog för lång tid.")
    except socket.gaierror as error:
        raise ValueError("DNS-adressen kunde inte hittas.") from error
    if not addresses or any(not public_address(info[4][0]) for info in addresses):
        raise ValueError("Interna, lokala, reserverade eller blandade publika/interna adresser nekas.")
    return parsed, host, port, addresses[0]


def check(url):
    deadline, current = time.monotonic() + 8, url
    for redirect in range(4):
        parsed, host, port, info = endpoint(current, deadline)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("Länkkontrollen tog för lång tid.")
        connection = (http.client.HTTPSConnection(host, port, timeout=remaining, context=ssl.create_default_context())
                      if parsed.scheme == "https" else http.client.HTTPConnection(host, port, timeout=remaining))
        # HTTPConnection retains the hostname for Host/SNI; only the validated address is connected.
        def pinned_connect(address, timeout, source_address=None):
            sock = socket.socket(info[0], info[1], info[2])
            try:
                sock.settimeout(timeout)
                sock.connect(info[4])
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Link deadline exceeded")
                sock.settimeout(remaining)
                return sock
            except OSError:
                sock.close()
                raise
        connection._create_connection = pinned_connect
        try:
            connection.connect()
            connection.sock = DeadlineSocket(connection.sock, deadline)
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            connection.request("HEAD", target, headers={"User-Agent": "Prylbanken-LinkCheck/1.0", "Accept": "*/*"})
            response = connection.getresponse()
            status, location = response.status, response.getheader("Location")
            if status in (301, 302, 303, 307, 308) and location:
                if redirect == 3:
                    raise ValueError("För många omdirigeringar (högst tre).")
                current = urljoin(current, location)
                continue
            return {"status": "ok" if 200 <= status < 400 else "http-error",
                    "detail": f"HTTP {status}" + (" – HEAD stöds inte; kontrollera länken manuellt." if status == 405 else ""),
                    "final_url": current}
        except (OSError, http.client.HTTPException) as error:
            raise ValueError("HTTP/TLS-kontrollen misslyckades: " + type(error).__name__) from error
        finally:
            connection.close()
    raise ValueError("Länkkontrollen kunde inte slutföras.")


def mutate(handler, db, method, path):
    import re
    match = re.fullmatch(r"/api/items/(\d+)/check-link", path)
    if not match or method != "POST":
        return False
    if not db.execute("SELECT 1 FROM settings WHERE key='link_check_enabled' AND value='true'").fetchone():
        raise ValueError("Länkkontrollen är avstängd. En administratör kan aktivera den.")
    item_id = int(match[1])
    row = db.execute("SELECT content FROM items WHERE id=? AND category='lankar' AND deleted_at IS NULL", (item_id,)).fetchone()
    if not row:
        raise FileNotFoundError("Posten är inte en aktiv webblänk.")
    now, uid = int(time.time()), handler.user["id"]
    db.execute("DELETE FROM link_attempts WHERE started<=?", (now - 300,))
    count = db.execute("SELECT attempts FROM link_attempts WHERE user_id=?", (uid,)).fetchone()
    if count and count["attempts"] >= 10:
        handler.reply(429, {"error": "Högst tio länkkontroller per fem minuter."}, headers={"Retry-After": "300"})
        return True
    db.execute("INSERT INTO link_attempts VALUES (?,?,1) ON CONFLICT(user_id) DO UPDATE SET attempts=attempts+1", (uid, now))
    db.commit()
    try:
        result = check(row["content"])
    except ValueError as error:
        db.execute("INSERT INTO link_checks(item_id,url,status,detail) VALUES (?,?,'blocked-or-error',?) "
                   "ON CONFLICT(item_id) DO UPDATE SET url=excluded.url,status=excluded.status,detail=excluded.detail,checked=CURRENT_TIMESTAMP",
                   (item_id, row["content"], str(error)))
        db.commit()
        raise
    db.execute("INSERT INTO link_checks(item_id,url,status,detail) VALUES (?,?,?,?) "
               "ON CONFLICT(item_id) DO UPDATE SET url=excluded.url,status=excluded.status,detail=excluded.detail,checked=CURRENT_TIMESTAMP",
               (item_id, row["content"], result["status"], result["detail"]))
    db.commit(); handler.reply(200, result)
    return True

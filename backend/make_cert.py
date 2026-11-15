"""Create a self-signed HTTPS certificate so phones/laptops are allowed to use the camera.
Usage:  python make_cert.py            (then restart `python app.py` - it switches to https automatically)
Browsers show a one-time warning for self-signed certificates: click Advanced -> Proceed."""
import datetime
import ipaddress
import os
import socket

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def lan_ips():
    ips = {"127.0.0.1"}
    try:                                    # the address other devices use to reach this laptop
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("10.255.255.255", 1)); ips.add(s.getsockname()[0]); s.close()
    except OSError:
        pass
    try:
        ips.update(i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    return sorted(ips)


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "certs")
    os.makedirs(out, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "QuickMark")])
    ips = lan_ips()
    san = [x509.DNSName("localhost")] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .sign(key, hashes.SHA256()))
    with open(os.path.join(out, "key.pem"), "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    with open(os.path.join(out, "cert.pem"), "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print("Certificate created in backend/certs/ for:", ", ".join(["localhost"] + ips))
    print("Restart the server: python app.py   ->   it will now use https://")


if __name__ == "__main__":
    main()

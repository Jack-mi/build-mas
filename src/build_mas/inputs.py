"""Material adapters that preserve provenance and never grant execution authority."""

import http.client
import ipaddress
import mimetypes
import socket
import ssl
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

from .errors import BuildMasError
from .workspace import has_secret, relative_file


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fragments = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.fragments.append(data.strip())


def public_url(url, *, with_addresses=False):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password or parsed.port not in {None, 80, 443}:
        raise BuildMasError("unsafe_url", "Only public HTTP(S) URLs without credentials are accepted")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise BuildMasError("unsafe_url", "Private and loopback destinations are forbidden")
    return (parsed, addresses) if with_addresses else parsed


def fetch_text(url):
    connection = None
    try:
        parsed, addresses = public_url(url, with_addresses=True)
        connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=15) if parsed.scheme == "https" else http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=15)
        family, kind, protocol, _, address = addresses[0]
        sock = socket.socket(family, kind, protocol)
        connection.sock = sock
        sock.settimeout(15)
        # Use the validated numeric address; reconnecting by hostname permits DNS rebinding.
        sock.connect(address)
        if parsed.scheme == "https":
            connection.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parsed.hostname)
        target = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        connection.request("GET", target, headers={"User-Agent": "build-mas/0.2", "Host": parsed.netloc})
        response = connection.getresponse()
        if response.status < 200 or response.status >= 300:
            raise BuildMasError("input_unavailable", "URL returned an error or redirect; redirects are not followed")
        payload = response.read(2000001)
        if len(payload) > 2000000:
            raise BuildMasError("input_limit", "URL content exceeds 2 MB")
        content = payload.decode("utf-8", errors="replace")
        media_type = response.headers.get_content_type()
    except BuildMasError:
        raise
    except Exception as exc:
        raise BuildMasError("input_unavailable", "URL could not be read safely", details={"type": type(exc).__name__}) from exc
    finally:
        if connection:
            connection.close()
    if media_type == "text/html":
        parser = VisibleText()
        parser.feed(content)
        content = "\n".join(parser.fragments)
    elif not media_type.startswith("text/") and media_type not in {"application/json", "application/xml"}:
        raise BuildMasError("unsupported_input", "Binary URLs must be downloaded as user-provided local files")
    if has_secret(content):
        raise BuildMasError("secret_detected", "Secret-like material was rejected")
    return content[:100000]


def normalize_materials(materials, root, stage, *, store=None, workspace_id=None):
    result = []
    images = []
    directory = Path(stage) / "_buildmas_inputs"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    for index, material in enumerate(materials):
        value = {"kind": material.kind, "source": material.source, "trust": "untrusted_reference", "media_type": material.media_type}
        if material.kind == "url":
            value["reference"] = material.uri or material.content
            value["content"] = fetch_text(value["reference"])
        elif material.path or material.asset_id:
            if material.asset_id:
                if store is None:
                    raise BuildMasError("asset_unavailable", "Material references require the owning asset registry")
                record = store.read("assets", material.asset_id)
                if record["workspace_id"] != workspace_id:
                    raise BuildMasError("scope_mismatch", "Attachment belongs to another workspace")
                path = Path(record["path"])
                import hashlib

                if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
                    raise BuildMasError("stale_input", "Registered attachment was changed")
                path_value = Path(record["file_name"])
            else:
                path_value = Path(material.path)
                if path_value.is_absolute():
                    try:
                        path_value = path_value.relative_to(Path(root).resolve())
                    except ValueError as exc:
                        raise BuildMasError("path_escape", "Material paths must be inside the registered workspace") from exc
                path = relative_file(root, path_value.as_posix())
            if not path.is_file() or path.stat().st_size > 10000000:
                raise BuildMasError("input_unavailable", "Material file is missing or exceeds 10 MB")
            if material.sha256:
                import hashlib

                if hashlib.sha256(path.read_bytes()).hexdigest() != material.sha256:
                    raise BuildMasError("stale_input", "Material no longer matches its supplied hash")
            value["reference"] = path_value.as_posix()
            if material.kind == "image":
                media_type = mimetypes.guess_type(path.name)[0]
                if media_type not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
                    raise BuildMasError("unsupported_input", "Unsupported image format")
                destination = directory / f"image_{index}{path.suffix}"
                destination.write_bytes(path.read_bytes())
                images.append(destination)
                value["local_image"] = str(destination)
            else:
                try:
                    if path.suffix.lower() == ".docx":
                        import zipfile
                        import xml.etree.ElementTree as ET

                        with zipfile.ZipFile(path) as archive:
                            item = archive.getinfo("word/document.xml")
                            if item.file_size > 2000000:
                                raise BuildMasError("input_limit", "Word document expansion exceeds 2 MB")
                            document = ET.fromstring(archive.read(item))
                        value["content"] = "\n".join(node.text or "" for node in document.iter() if node.tag.endswith("}t"))[:100000]
                    elif path.suffix.lower() == ".pdf":
                        import shutil
                        import subprocess

                        binary = shutil.which("pdftotext")
                        if not binary:
                            raise BuildMasError("unsupported_input", "PDF extraction requires pdftotext; import extracted text or page images instead")
                        from .templates.execution import bounded_output
                        from .verify import sandbox_command
                        temporary = directory / f"pdf_{index}"
                        temporary.mkdir()
                        command = sandbox_command([binary, "-layout", str(path), "-"], path.parent, temporary)
                        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
                        extracted, error = bounded_output(process, timeout=20, max_bytes=2000000)
                        if process.returncode != 0 or error:
                            raise BuildMasError("input_unavailable", "PDF extraction failed or exceeded limits")
                        value["content"] = extracted.decode("utf-8", errors="replace")[:100000]
                    else:
                        value["content"] = path.read_text(encoding="utf-8")[:100000]
                except UnicodeError as exc:
                    raise BuildMasError("unsupported_input", "Binary document requires a text extraction adapter; supply extracted text or images") from exc
        elif material.uri:
            raise BuildMasError("unsupported_input", "Use a local path or an explicitly supported URL input")
        else:
            value["content"] = material.content
        if has_secret(value.get("content", "")):
            raise BuildMasError("secret_detected", "Secret-like input was rejected")
        result.append(value)
    return result, images

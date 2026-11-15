"""CSP for both local web desks, calculated from the HTML actually served."""
import base64
import hashlib
from html.parser import HTMLParser
import os
from urllib.parse import urlsplit


class _Scripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.script = None
        self.hashes = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.script = [] if 'src' not in dict(attrs) else None

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.script is not None:
            digest = hashlib.sha256(''.join(self.script).encode('utf-8')).digest()
            self.hashes.append("'sha256-" + base64.b64encode(digest).decode('ascii') + "'")
            self.script = None


def fax_origins():
    """Explicit deployment opt-in for custom news feeds, never arbitrary http(s):."""
    origins = []
    for value in os.environ.get('DISCPROBE_FAX_ORIGINS', '').split():
        url = urlsplit(value)
        if (url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password
                or url.path not in ('', '/') or url.query or url.fragment
                or any(c in value for c in "*;'\"\\")):
            raise ValueError('DISCPROBE_FAX_ORIGINS must contain only http(s) origins')
        origins.append(url.scheme + '://' + url.netloc)
    return sorted(set(origins))


def content_security_policy(body, *, fax=False):
    # HTML input preprocessing normalizes line endings before CSP hashes are checked.
    html = body.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
    scripts = _Scripts()
    scripts.feed(html)
    sources = "'self'" + ''.join(' ' + origin for origin in fax_origins()) if fax else "'self'"
    # dev-photo builds an isolated preview module from the installed calibration code.
    blob_script = ' blob:' if 'URL.createObjectURL(new Blob([head + source + tail]' in html else ''
    return '; '.join([
        "default-src 'self'",
        "script-src 'self'" + blob_script + ''.join(' ' + h for h in sorted(set(scripts.hashes))),
        "style-src 'self' 'unsafe-inline'",  # generated styles and style attributes throughout both desks
        'connect-src ' + sources,
        'img-src ' + sources + ' data: blob:',
        "font-src 'self'",
        "worker-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])

import os
import posixpath
import http.server
import urllib.request, urllib.parse, urllib.error
import cgi
import sys
import mimetypes
import zlib
import webbrowser

from optparse import OptionParser

try:
    from io import StringIO
except ImportError:
    from io import StringIO

SERVER_PORT = 55000
IP_ADDRESS = '0.0.0.0'
encoding_type = 'gzip'

def parse_options():
    # Option parsing logic.
    parser = OptionParser()
    parser.add_option("-e", "--encoding", dest="encoding_type",
                      help="Encoding type for server to utilize",
                      metavar="ENCODING", default='gzip')
    global SERVER_PORT
    parser.add_option("-p", "--port", dest="port", default=SERVER_PORT,
                      help="The port to serve the files on",
                      metavar="ENCODING")
    (options, args) = parser.parse_args()
    global encoding_type
    encoding_type = options.encoding_type
    SERVER_PORT = int(options.port)

    if encoding_type not in ['zlib', 'deflate', 'gzip']:
        sys.stderr.write("Please provide a valid encoding_type for the server to utilize.\n")
        sys.stderr.write("Possible values are 'zlib', 'gzip', and 'deflate'\n")
        sys.stderr.write("Usage: python GzipSimpleHTTPServer.py --encoding=<encoding_type>\n")
        sys.exit()


def zlib_encode(content):
    zlib_compress = zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS)
    data = zlib_compress.compress(content) + zlib_compress.flush()
    return data


def deflate_encode(content):
    deflate_compress = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    data = deflate_compress.compress(content) + deflate_compress.flush()
    return data


def gzip_encode(content):
    gzip_compress = zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS | 16)
    data = gzip_compress.compress(content) + gzip_compress.flush()
    return data


class SimpleHTTPRequestHandler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        """Serve a GET request."""
        content = self.send_head()
        if content:
            self.wfile.write(content)

    def do_HEAD(self):
        """Serve a HEAD request."""
        content = self.send_head()

    def send_head(self):

        path = self.translate_path(self.path)
        print(("Serving path '%s'" % path))
        f = None
        if os.path.isdir(path):
            if not self.path.endswith('/'):
                # redirect browser - doing basically what apache does
                self.send_response(301)
                self.send_header("Location", self.path + "/")
                self.end_headers()
                return None
            for index in "index.html", "index.htm":
                index = os.path.join(path, index)
                if os.path.exists(index):
                    path = index
                    break
            else:
                return self.list_directory(path).read()
        ctype = self.guess_type(path)
        try:
            # Always read in binary mode. Opening files in text mode may cause
            # newline translations, making the actual size of the content
            # transmitted *less* than the content-length!
            f = open(path, 'rb')
        except IOError:
            self.send_error(404, "File not found")
            return None
        self.send_response(200)
        self.send_header("Content-type", ctype)
        self.send_header("Content-Encoding", encoding_type)
        fs = os.fstat(f.fileno())
        raw_content_length = fs[6]
        content = f.read()

        # Encode content based on runtime arg
        if encoding_type == "gzip":
            content = gzip_encode(content)
        elif encoding_type == "deflate":
            content = deflate_encode(content)
        elif encoding_type == "zlib":
            content = zlib_encode(content)

        compressed_content_length = len(content)
        f.close()
        self.send_header("Content-Length", max(raw_content_length, compressed_content_length))
        self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
        self.end_headers()
        return content

    def list_directory(self, path):

        try:
            list = os.listdir(path)
        except os.error:
            self.send_error(404, "No permission to list directory")
            return None
        list.sort(key=lambda a: a.lower())
        f = StringIO()
        displaypath = cgi.escape(urllib.parse.unquote(self.path))
        f.write('<!DOCTYPE html>')
        f.write("<html>\n<title>Directory listing for %s</title>\n" % displaypath)
        f.write("<body>\n<h2>Directory listing for %s</h2>\n" % displaypath)
        f.write("<hr>\n<ul>\n")
        for name in list:
            fullname = os.path.join(path, name)
            displayname = linkname = name
            # Append / for directories or @ for symbolic links
            if os.path.isdir(fullname):
                displayname = name + "/"
                linkname = name + "/"
            if os.path.islink(fullname):
                displayname = name + "@"
                # Note: a link to a directory displays with @ and links with /
            f.write('<li><a href="%s">%s</a>\n'
                    % (urllib.parse.quote(linkname), cgi.escape(displayname)))
        f.write("</ul>\n<hr>\n</body>\n</html>\n")
        length = f.tell()
        f.seek(0)
        self.send_response(200)
        encoding = sys.getfilesystemencoding()
        self.send_header("Content-type", "text/html; charset=%s" % encoding)
        self.send_header("Content-Length", str(length))
        self.end_headers()
        return f

    def translate_path(self, path):

        # abandon query parameters
        path = path.split('?',1)[0]
        path = path.split('#',1)[0]
        path = posixpath.normpath(urllib.parse.unquote(path))
        words = path.split('/')
        words = [_f for _f in words if _f]
        path = os.getcwd()
        for word in words:
            drive, word = os.path.splitdrive(word)
            head, word = os.path.split(word)
            if word in (os.curdir, os.pardir): continue
            path = os.path.join(path, word)
        return path

    def guess_type(self, path):
	
        base, ext = posixpath.splitext(path)
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        ext = ext.lower()
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        else:
            return self.extensions_map['']

    if not mimetypes.inited:
        mimetypes.init() # try to read system mime.types
    extensions_map = mimetypes.types_map.copy()
    extensions_map.update({
        '': 'application/octet-stream', # Default
        '.py': 'text/plain',
        '.c': 'text/plain',
        '.h': 'text/plain',
        })


def test(HandlerClass = SimpleHTTPRequestHandler,
         ServerClass = http.server.HTTPServer):

	parse_options()

	server_address = (IP_ADDRESS, SERVER_PORT)

	SimpleHTTPRequestHandler.protocol_version = "HTTP/1.0"

	httpd = http.server.HTTPServer(server_address, SimpleHTTPRequestHandler)

	sa = httpd.socket.getsockname()
	print("Serving HTTP on", sa[0], "port", sa[1], "...")

	address = "http://localhost:"+ str(sa[1])
	webbrowser.open_new(address)
	httpd.serve_forever()
	http.server.test(HandlerClass, ServerClass)

if __name__ == '__main__':
	test()
import socket, os, logging
from mimetypes import guess_type
from datetime import datetime
from urllib.parse import parse_qsl
from json import dumps

ADDRESS = "127.0.0.1"
PORT = 8050
BUFFER_SIZE = 2048
ENCODING_FORMAT = "utf-8"
TIME_FORMAT = "%A, %d %b %Y %H:%M:%S GMT"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("access.log"),
        logging.StreamHandler()
    ]
)

def access_log(client_addr, method, path, status_code, uagent):
    logging.info(f'{client_addr} - \"{method}" "{path}\" {status_code} {uagent}')

def parse_request(raw_req: str, conn: bytes) -> dict:
    break_line = "\r\n"
    headers = dict()
    split_request = raw_req.split(break_line)
    
    # Request line
    headers["method"], headers["path"], headers["http_version"] = split_request.pop(0).split(" ")

    # Header fields
    for f in split_request:
        if len(f) < 2:
            break
        key, value = f.split(": ", 1)
        headers[key] = value
    
    # Chunked Transfer
    if "Content-Length" in headers:
        content_length = int(headers["Content-Length"])
        body = raw_req.split(break_line * 2)[-1]
        while len(body) < content_length:
            body += conn.recv(BUFFER_SIZE).decode(ENCODING_FORMAT)
        headers["body"] = body
    return headers

def resp_line(status_code: int, http_ver="HTTP/1.1") -> bytes:
    # Construct response line
    codes = {
        200: 'OK',
        204: 'No Content',
        404: 'Not Found',
        501: 'Not Implemented'
    }
    response = f"{http_ver} {status_code} {codes[status_code]}\r\n"
    return response.encode(ENCODING_FORMAT)

def resp_headers(fields: dict) -> bytes:
    # Construct response headers
    basic_headers = {
        "Server": "SIMP-HTTP",
        "Connection": "keep-alive",
    }
    basic_headers.update(fields)
    response = ""
    for key, value in basic_headers.items():
        response += f"{key}: {value}\r\n"
    response += "\r\n"
    return response.encode(ENCODING_FORMAT)

def directory_page(directory: str) -> str:
    items = os.listdir(directory)
    list_items = ""
    for item in items:
        path = os.path.join(directory, item)
        if os.path.isdir(path):
            list_items += f'<li><a href="{item}/">{item}/</a></li>'
        else:
            list_items += f'<li><a href="{item}">{item}</a></li>'
    
    html_template = f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Directory Listing</title>
                <link rel="stylesheet" href="/styles/directory.css">
            </head>
            <body>
                <div class="container">
                    <h1>Directory Listing</h1>
                    <ul>
                        {list_items}
                    </ul>
                </div>
            </body>
            </html>
    """
    return html_template
    
def handle_get(req_path: str, addr: str, agent: str) -> bytes:
    # Directory listing
    if req_path == "/":
        payload = directory_page(".").encode(ENCODING_FORMAT)
        content_type = "text/html"
        headers = {
            "Content-Type": f"{content_type}",
            "Content-Length": len(payload),
            "Date": datetime.now().strftime(TIME_FORMAT),
        }
        response_line = resp_line(200)
        response_headers = resp_headers(headers)
        server_resp = response_line + response_headers + payload
        access_log(addr, "GET", req_path, 200, agent)
        return server_resp
    
    file_or_dir = req_path.lstrip("/")

    # path is a directory -> list its contents
    if os.path.exists(file_or_dir) and os.path.isdir(file_or_dir):
        payload = directory_page(file_or_dir).encode(ENCODING_FORMAT)
        content_type = "text/html"
        headers = {
            "Content-Type": f"{content_type}",
            "Content-Length": len(payload),
            "Date": datetime.now().strftime(TIME_FORMAT),
        }
        response_line = resp_line(200)
        response_headers = resp_headers(headers)
        server_resp = response_line + response_headers + payload
        access_log(addr, "GET", req_path, 200, agent)
        return server_resp

    # path is a file -> serve it
    if os.path.exists(file_or_dir) and os.path.isfile(file_or_dir):
        with open(file_or_dir, 'rb') as f:
            payload = f.read()
        content_type = guess_type(file_or_dir)[0] or "text/html"
        headers = {
            "Content-Type": f"{content_type}",
            "Content-Length": len(payload),
            "Date": datetime.now().strftime(TIME_FORMAT),
            "Last-Modified": datetime.fromtimestamp(os.path.getmtime(file_or_dir)).strftime(TIME_FORMAT),
        }
        response_line = resp_line(200)
        response_headers = resp_headers(headers)
        server_resp = response_line + response_headers + payload
        access_log(addr, "GET", req_path, 200, agent)
        return server_resp

    access_log(addr, "GET", req_path, 404, agent)
    return handle_404()

def handle_options(req_path: str, addr: str, agent: str) -> bytes:
    headers = {
        "Allow": "GET, POST, OPTIONS",
        "Date": datetime.now().strftime(TIME_FORMAT),
    }
    response_line = resp_line(204)
    response_headers = resp_headers(headers)
    server_resp = response_line + response_headers
    access_log(addr, "OPTIONS", req_path, 204, agent)
    return server_resp

def handle_post(data: str, req_path: str, agent: str, addr: str) -> bytes:
    info = list()
    parse_query = dict(parse_qsl(data))
    info.append(parse_query)
    data_file_path = "data/info.json"
    with open(f"{data_file_path}", 'wb') as f:
        f.write(dumps(info, indent=4, ensure_ascii=True).encode(ENCODING_FORMAT))

    payload = "<h1>Data Saved successfully!</h1>"
    content_type = guess_type(payload)[0] or "text/html"
    headers = {
        "Content-Type": f"{content_type}",
        "Content-Length": len(payload),
        "Date": datetime.now().strftime(TIME_FORMAT)
    }
    response_line = resp_line(200)
    response_headers = resp_headers(headers)
    server_resp = response_line + response_headers + payload.encode(ENCODING_FORMAT)
    access_log(addr, "POST", req_path, 200, agent)
    return server_resp

def handle_404() -> bytes:
    # 404 Not Found HTML Response
    http_template = """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>404 Not Found</title>
                <link rel="stylesheet" href="/styles/404.css">
            </head>
            <body>
                <div class="container">
                    <h1>Oops...404 NOT FOUND</h1>
                </div>
            </body>
            </html>
    """
    payload = http_template.encode(ENCODING_FORMAT)
    headers = {
        "Content-Type": "text/html",
        "Content-Length": len(payload),
        "Date": datetime.now().strftime(TIME_FORMAT),
    }
    response_line = resp_line(404)
    response_headers = resp_headers(headers)
    return response_line + response_headers + payload

def handle_501(method: str, addr: str, req_path: str, agent: str) -> bytes:
    payload = "<h1>501 Not Implemented</h1>"
    content_type = guess_type(payload)[0] or "text/html"
    headers = {
        "Server": "SIMP-HTTP",
        "Content-Type": f"{content_type}",
        "Content-Length": len(payload),
        "Date": datetime.now().strftime(TIME_FORMAT)
    }
    response_line = resp_line(501)
    response_headers = resp_headers(headers)
    server_resp = response_line + response_headers + payload.encode(ENCODING_FORMAT)
    access_log(addr, f"{method}", req_path, 501, agent)
    return server_resp

def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((ADDRESS, PORT))
    server_socket.listen()
    print(f"Server started on {ADDRESS}:{PORT}")

    while True:
        client_conn, client_addr = server_socket.accept()
        print(f"Connection from {client_addr}")
        while True:
            msg = client_conn.recv(BUFFER_SIZE).decode(ENCODING_FORMAT)
            if not msg:
                break
            header_fields = parse_request(msg, client_conn)
            if header_fields["method"] == "GET":
                client_conn.send(handle_get(header_fields["path"], client_addr, header_fields.get("User-Agent", "")))
            elif header_fields["method"] == "POST":
                client_conn.send(handle_post(header_fields["body"], header_fields["path"], header_fields.get("User-Agent", ""), client_addr))
            elif header_fields["method"] == "OPTIONS":
                client_conn.send(handle_options(header_fields["path"], client_addr, header_fields.get("User-Agent", "")))
            else:
                client_conn.send(handle_501(header_fields["method"], client_addr, header_fields["path"], header_fields.get("User-Agent", "")))
        client_conn.close()

if __name__ == "__main__":
    main()
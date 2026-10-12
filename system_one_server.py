"""Optional loopback Laya bridge. Run in a separate environment with laya installed."""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from system_one import LIMIT, validate_request, validate_response


def handler(agent, model):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.connection.settimeout(10)
            if self.path != '/v1/systemone':
                self.send_error(404)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= LIMIT:
                    raise ValueError('Invalid decision request.')
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or payload.get('model') != model:
                    raise ValueError('Invalid model connection.')
                state, questions = payload.get('state'), payload.get('questions')
                validate_request(state, questions)
            except (ValueError, TypeError, UnicodeError):
                self.send_error(400)
                return
            try:
                result = validate_response(agent.predict(state, questions), questions)
                result['model'] = model
                body = json.dumps(result, allow_nan=False).encode()
                if len(body) > LIMIT: raise ValueError('Response too large')
            except Exception:
                self.send_error(500)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass  # State and questions are not logged.
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8001)
    parser.add_argument('--model', default='convaiinnovations/laya')
    parser.add_argument('--subfolder', choices=['multilingual', 'typed-decisions'])
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--threads', type=int, default=4)
    args = parser.parse_args()
    if args.threads < 1: parser.error('--threads must be positive')
    import torch
    torch.set_num_threads(args.threads)
    import laya
    agent = laya.load(args.model, device=args.device, subfolder=args.subfolder)
    with HTTPServer(('127.0.0.1', args.port), handler(agent, args.model)) as server:
        server.serve_forever()


if __name__ == '__main__':
    main()

"""External Android broadcast substitute for isolated install/IPC acceptance.

Executed through PATH as termux-am/am. It speaks the actual sockets/JSON wire,
records decoded pixels and positions, and exits when the daemon disconnects.
It never imports or patches the application under test.
"""
import base64
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
from PIL import Image


def serve(main_address, event_address):
    done = threading.Event()
    with socket.socket(socket.AF_UNIX) as main, socket.socket(socket.AF_UNIX) as events:
        main.connect('\0' + main_address)
        events.connect('\0' + event_address)
        main.settimeout(180)

        def exact(n):
            data = b''
            while len(data) < n:
                part = main.recv(n - len(data))
                if not part:
                    raise EOFError
                data += part
            return data

        def reply(value, stream=main):
            body = json.dumps(value).encode()
            stream.sendall(len(body).to_bytes(4, 'big') + body)

        def emit_input():
            path = Path(os.environ['PET_TEST_ROOT']) / 'touch.jsonl'
            with path.open('a+') as source:
                source.seek(0, 2)
                while not done.wait(.01):
                    line = source.readline()
                    if line:
                        try:
                            reply(json.loads(line), events)
                        except OSError:
                            return

        thread = threading.Thread(target=emit_input, daemon=True)
        log = Path(os.environ['PET_TEST_ROOT']) / 'renderer.jsonl'
        try:
            if exact(1) != b'\1':
                raise ValueError('Invalid handshake')
            main.sendall(b'\0')
            thread.start()
            while True:
                message = json.loads(exact(int.from_bytes(exact(4), 'big')))
                method = message['method']
                params = message.get('params', {})
                if method in ('newActivity', 'createLinearLayout', 'createImageView'):
                    reply({'newActivity': 1, 'createLinearLayout': 2,
                          'createImageView': 3}[method])
                elif method == 'getVersion':
                    # Unverified version must always select conservative PNG.
                    reply(8)
                elif method == 'getDimensions':
                    reply([192, 192])
                elif method == 'setImage':
                    with Image.open(BytesIO(base64.b64decode(params['img']))) as img:
                        row = {'method': method, 'size': img.size,
                               'rgba_sha256': hashlib.sha256(img.convert('RGBA').tobytes()).hexdigest()}
                    with log.open('a') as output:
                        output.write(json.dumps(row) + '\n')
                elif method == 'setPosition':
                    with log.open('a') as output:
                        output.write(json.dumps(
                            {'method': method, 'x': params['x'], 'y': params['y']}) + '\n')
        except (EOFError, OSError):
            pass
        finally:
            done.set()
            if thread.ident is not None:
                thread.join(1)


if __name__ == '__main__':
    if sys.argv[1] == '--serve':
        serve(*sys.argv[2:4])
    else:
        main_address = sys.argv[sys.argv.index('mainSocket') + 1]
        event_address = sys.argv[sys.argv.index('eventSocket') + 1]
        subprocess.Popen([sys.executable, __file__, '--serve', main_address, event_address],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)

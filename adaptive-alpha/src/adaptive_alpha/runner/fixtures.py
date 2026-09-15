"""Fixed acceptance programs. Development runc never accepts supplied source."""

FIXTURES = {
    "echo": "def run(payload):\n    return {'echo': payload}\n",
    "boundaries": """def run(payload):
    import os, signal, socket
    denied = []
    for path in ['/run/secrets/operator_token', '/var/run/docker.sock', '/app/src/adaptive_alpha/risk/engine.py']:
        try:
            open(path).close()
        except OSError:
            denied.append(path)
    try:
        open('/etc/ouromarket-write-probe', 'w').close()
        readonly = False
    except OSError:
        readonly = True
    try:
        os.kill(os.getppid(), signal.SIGSTOP)
        watchdog_protected = False
    except PermissionError:
        watchdog_protected = True
    try:
        os.setuid(0)
        root_denied = False
    except PermissionError:
        root_denied = True
    with open('/proc/self/status') as status:
        capabilities = {line.split(':')[0]: line.split(':')[1].strip() for line in status if line.startswith(('CapEff:', 'CapPrm:'))}
    sock = socket.socket()
    sock.settimeout(0.2)
    try:
        sock.connect(('192.0.2.1', 443))
        network_denied = False
    except OSError:
        network_denied = True
    finally:
        sock.close()
    return dict(uid=os.getuid(), denied=denied, readonly=readonly, watchdog_protected=watchdog_protected, network_denied=network_denied, root_denied=root_denied, capabilities=capabilities)
""",
    "timeout": "def run(payload):\n    while True:\n        pass\n",
    "output": "def run(payload):\n    print('x' * 100000)\n    return None\n",
    "stderr": "def run(payload):\n    import sys\n    sys.stderr.write('x' * 100000)\n    return None\n",
    "invalid": "def run(payload):\n    print('not json')\n    return None\n",
    "failure": "def run(payload):\n    raise RuntimeError('controlled failure')\n",
    "children": """def run(payload):
    import os, time
    for _ in range(100):
        try:
            pid = os.fork()
        except OSError:
            break
        if pid == 0:
            os.setsid()
            while True:
                time.sleep(1)
    while True:
        time.sleep(1)
""",
    "memory": "def run(payload):\n    return len(bytearray(512 * 1024 * 1024))\n",
    "workspace": """def run(payload):
    from pathlib import Path
    path = Path('/tmp/previous-job')
    existed = path.exists()
    path.write_text('test')
    return {'previous_exists': existed}
""",
}

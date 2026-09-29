#!/usr/bin/env python3
"""Linux acceptance harness: deny socket syscalls in this process and descendants.

Usage: python scripts/without_network.py COMMAND [ARGS...]
Requires libseccomp; no root privileges or network namespace support needed.
This is a test harness, not a general-purpose sandbox for untrusted programs.
"""

import ctypes
import ctypes.util
import errno
import json
import os
import socket
import sys


def deny_network():
    library = ctypes.util.find_library("seccomp")
    if not library:
        raise RuntimeError("libseccomp is required for enforced offline testing")
    lib = ctypes.CDLL(library, use_errno=True)
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    lib.seccomp_rule_add.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    lib.seccomp_rule_add.restype = ctypes.c_int
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_load.restype = ctypes.c_int
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.restype = None
    context = lib.seccomp_init(0x7FFF0000)  # SCMP_ACT_ALLOW
    if not context:
        raise RuntimeError("seccomp_init failed")
    try:
        # Also block sends on inherited descriptors; reads/local file IO remain.
        for name in (
            "socket",
            "socketpair",
            "connect",
            "bind",
            "listen",
            "accept",
            "accept4",
            "sendto",
            "sendmsg",
            "sendmmsg",
            "socketcall",
            "io_uring_setup",
        ):
            number = lib.seccomp_syscall_resolve_name(name.encode())
            if (
                number >= 0
                and lib.seccomp_rule_add(context, 0x00050000 | errno.EPERM, number, 0)
                != 0
            ):
                raise RuntimeError("Cannot deny " + name)
        if lib.seccomp_load(context) != 0:
            raise RuntimeError("Cannot load network-denial filter")
    finally:
        lib.seccomp_release(context)
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError as exc:
        if exc.errno != errno.EPERM:
            raise
    else:
        probe.close()
        raise RuntimeError("Network denial self-test failed")
    print(
        json.dumps({"network_policy": "seccomp-deny-sockets", "probe": "EPERM"}),
        file=sys.stderr,
        flush=True,
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    deny_network()
    os.execvp(sys.argv[1], sys.argv[1:])

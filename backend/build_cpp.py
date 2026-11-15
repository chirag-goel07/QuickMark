"""The C++ core (backend/cpp): how Flask finds its shared library.

Order used when the server starts:
  1. cpp/prebuilt/<system>/   ready-made library shipped with the project (Windows 64-bit and Linux 64-bit) - NO compiler needed
  2. cpp/build/               a library you built yourself
  3. compile it now           only if 1 and 2 are not usable; needs ONE C++17 compiler (g++ / clang++ / Visual Studio cl)

    python build_cpp.py            build it yourself into cpp/build/
    python build_cpp.py --test     build + run the native C++ tests
    python build_cpp.py --prebuilt refresh cpp/prebuilt/<this system>/ (for the person who edits the C++)
"""
import hashlib
import os
import platform
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CPP = os.path.join(HERE, "cpp")
OUT = os.path.join(CPP, "build")
SOURCES = ["quickmark_core.cpp"]
HEADERS = ["rate_limiter.hpp", "face.hpp", "stats.hpp", "csv_writer.hpp"]


def lib_path():
    name = "quickmark_core.dll" if sys.platform == "win32" else ("libquickmark_core.dylib" if sys.platform == "darwin" else "libquickmark_core.so")
    return os.path.join(OUT, name)


def system_tag():
    """e.g. windows-x64, linux-x64, macos-arm64"""
    sysname = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    machine = platform.machine().lower()
    arch = "x64" if machine in ("amd64", "x86_64") else ("arm64" if machine in ("arm64", "aarch64") else machine)
    return f"{sysname}-{arch}"


def python_bits():
    return struct.calcsize("P") * 8


def sources_hash():
    h = hashlib.sha256()
    for f in sorted(SOURCES + HEADERS):
        with open(os.path.join(CPP, f), "rb") as fh:
            h.update(fh.read().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def prebuilt_dir():
    return os.path.join(CPP, "prebuilt", system_tag())


def prebuilt_path():
    """The shipped library for THIS system, only if it was made from exactly the current C++ source; else None."""
    path = os.path.join(prebuilt_dir(), os.path.basename(lib_path()))
    stamp = os.path.join(prebuilt_dir(), "SOURCE_HASH")
    try:
        if os.path.exists(path) and open(stamp).read().strip() == sources_hash():
            return path
    except OSError:
        pass
    return None


def candidates():
    """Libraries to try loading, best first (the third option, compiling, is done by the caller)."""
    out = []
    if prebuilt_path():
        out.append(prebuilt_path())
    if os.path.exists(lib_path()) and not needs_build():
        out.append(lib_path())
    return out


def needs_build():
    lib = lib_path()
    if not os.path.exists(lib):
        return True
    newest = max(os.path.getmtime(os.path.join(CPP, f)) for f in SOURCES + HEADERS)
    return newest > os.path.getmtime(lib)


def build(verbose=False):
    os.makedirs(OUT, exist_ok=True)
    lib, src = lib_path(), [os.path.join(CPP, s) for s in SOURCES]
    attempts = []
    for cc in ("g++", "clang++", "c++"):
        if shutil.which(cc):
            cmd = [cc, "-std=c++17", "-O2", "-shared", "-o", lib] + src
            if sys.platform != "win32":
                cmd.insert(4, "-fPIC")
            if sys.platform == "win32" or sys.platform.startswith("linux"):
                cmd += ["-static-libgcc", "-static-libstdc++"]            # no extra runtime libraries needed on other computers
            attempts.append(cmd)
            break
    if sys.platform == "win32" and shutil.which("cl"):
        attempts.append(["cl", "/nologo", "/std:c++17", "/O2", "/EHsc", "/LD"] + src + ["/Fe" + lib, "/Fo" + OUT + os.sep])
    if not attempts:
        raise RuntimeError("No C++ compiler found. Install g++ (MinGW/MSYS2 on Windows, build-essential on Linux, Xcode tools on Mac) "
                           "or Visual Studio Build Tools, then run:  python build_cpp.py")
    last = None
    for cmd in attempts:
        if verbose:
            print(" ".join(cmd))
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=OUT)
        if r.returncode == 0 and os.path.exists(lib):
            return lib
        last = r.stdout + r.stderr
    raise RuntimeError("Building the C++ core failed:\n" + (last or ""))


def run_native_tests():
    exe = os.path.join(OUT, "test_core.exe" if sys.platform == "win32" else "test_core")
    os.makedirs(OUT, exist_ok=True)
    cc = next((c for c in ("g++", "clang++", "c++") if shutil.which(c)), None)
    if not cc:
        raise RuntimeError("Native tests need g++ or clang++.")
    subprocess.run([cc, "-std=c++17", "-O2", "-Wall", "-Wextra", "-o", exe, os.path.join(CPP, "tests", "test_core.cpp")], check=True)
    return subprocess.run([exe]).returncode


def refresh_prebuilt():
    built = build(verbose=True)
    os.makedirs(prebuilt_dir(), exist_ok=True)
    shutil.copy2(built, os.path.join(prebuilt_dir(), os.path.basename(built)))
    with open(os.path.join(prebuilt_dir(), "SOURCE_HASH"), "w") as f:
        f.write(sources_hash())
    return prebuilt_dir()


if __name__ == "__main__":
    if "--prebuilt" in sys.argv:
        print("prebuilt refreshed in:", refresh_prebuilt())
        sys.exit(0)
    print("built:", build(verbose=True))
    if "--test" in sys.argv:
        sys.exit(run_native_tests())

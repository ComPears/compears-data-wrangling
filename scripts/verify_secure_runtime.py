"""Fail closed on vulnerable installer, CA bundle or Playwright Node runtime."""
import importlib.metadata
import json
import re
import subprocess
import sys

from playwright._impl._driver import compute_driver_executable


def version_tuple(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"v?\d+(?:\.\d+)+", value):
        raise ValueError(f"Expected a stable version, got {value!r}")
    return tuple(int(part) for part in value.removeprefix("v").split("."))


def node_is_patched(value: str) -> bool:
    version = version_tuple(value)
    minimum = {22: (22, 23, 4), 24: (24, 22, 1), 26: (26, 12, 1)}
    return version[0] in minimum and version >= minimum[version[0]]


def main() -> None:
    if sys.version_info < (3, 12, 15):
        raise RuntimeError("Use Python 3.12.15 or newer")
    for package, minimum in (("pip", "26.2.2"), ("certifi", "2026.10.19")):
        installed = importlib.metadata.version(package)
        if version_tuple(installed) < version_tuple(minimum):
            raise RuntimeError(f"Upgrade {package} to >= {minimum}; got {installed}")
    node, _ = compute_driver_executable()
    result = subprocess.run([node, "--version"], check=True, capture_output=True, text=True)
    version = result.stdout.strip()
    if not node_is_patched(version):
        raise RuntimeError(f"Playwright uses vulnerable Node {version}. Set PLAYWRIGHT_NODEJS_PATH to patched Node.")
    print(json.dumps({"python": sys.version.split()[0], "playwright_node": version,
                      "pip": importlib.metadata.version("pip"), "certifi": importlib.metadata.version("certifi")}))


if __name__ == "__main__":
    main()

"""Normal frontend and private systemd helper entry points, including inside the zipapp."""

import sys


def main() -> int:
    sys.dont_write_bytecode = True
    if sys.argv[1:2] == ["--bt-keyboard"]:
        from legacy_bridge import main as bridge_main
        return bridge_main(sys.argv[2:])
    from frontend import main as frontend_main
    return frontend_main()

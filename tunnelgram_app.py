from __future__ import annotations

import multiprocessing
import sys


def main() -> None:
    multiprocessing.freeze_support()

    mode = "--gui"

    if len(sys.argv) > 1 and sys.argv[1] in {"--gui", "--proxy", "--diagnostics"}:
        mode = sys.argv[1]
        sys.argv = [sys.argv[0]] + sys.argv[2:]

    if mode == "--proxy":
        from tunnelgram.local_proxy import main as proxy_main

        proxy_main()
        return

    if mode == "--diagnostics":
        from tunnelgram.diagnostics import main as diagnostics_main

        diagnostics_main()
        return

    from tunnelgram.gui import main as gui_main

    gui_main()


if __name__ == "__main__":
    main()
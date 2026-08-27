"""Servidor mínimo mostrado mientras BFGenda está cerrada."""

from __future__ import annotations

import atexit
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = BASE_DIR / "runtime"
PID_FILE = RUNTIME_DIR / "bfgenda_espera.pid"

HOST = "0.0.0.0"
PORT = 8000

PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#6657d9">
    <meta name="robots" content="noindex,nofollow">
    <title>BFGenda está cerrada</title>

    <style>
        :root {
            color-scheme: light;
            font-family:
                Inter,
                system-ui,
                -apple-system,
                BlinkMacSystemFont,
                "Segoe UI",
                sans-serif;
            background: #f5f4fb;
            color: #29263a;
        }

        * {
            box-sizing: border-box;
        }

        html {
            min-height: 100%;
            overflow-x: hidden;
        }

        body {
            position: fixed;
            inset: 0;
            width: 100%;
            height: 100vh;
            height: 100dvh;
            min-height: 0;
            margin: 0;
            display: grid;
            place-items: center;
            padding: 24px;
            overflow: hidden;
            overscroll-behavior: none;
            background:
                radial-gradient(
                    circle at top,
                    rgba(102, 87, 217, 0.13),
                    transparent 42%
                ),
                #f5f4fb;
        }

        main {
            width: min(100%, 470px);
        }

        .card {
            padding: 34px 28px;
            border: 1px solid rgba(102, 87, 217, 0.16);
            border-radius: 24px;
            background: rgba(255, 255, 255, 0.96);
            box-shadow: 0 20px 55px rgba(50, 42, 101, 0.13);
            text-align: center;
        }

        .symbol {
            width: 72px;
            height: 72px;
            margin: 0 auto 22px;
            display: grid;
            place-items: center;
            border-radius: 21px;
            background: #eeeafd;
            color: #6657d9;
        }

        .symbol svg {
            width: 40px;
            height: 40px;
        }

        .eyebrow {
            margin: 0 0 7px;
            color: #6657d9;
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.09em;
            text-transform: uppercase;
        }

        h1 {
            margin: 0;
            font-size: clamp(1.65rem, 7vw, 2.1rem);
            line-height: 1.15;
        }

        .description {
            margin: 16px auto 0;
            color: #6c687b;
            font-size: 1rem;
            line-height: 1.6;
        }

        .notice {
            margin-top: 24px;
            padding: 15px 16px;
            border-radius: 14px;
            background: #f4f2fd;
            color: #514b70;
            font-size: 0.9rem;
            line-height: 1.5;
        }

        .retry {
            width: 100%;
            min-height: 48px;
            margin-top: 20px;
            border: 0;
            border-radius: 13px;
            background: #6657d9;
            color: #ffffff;
            cursor: pointer;
            font: inherit;
            font-weight: 800;
        }

        .retry:hover {
            background: #5849cc;
        }

        .retry:focus-visible {
            outline: 3px solid rgba(102, 87, 217, 0.3);
            outline-offset: 3px;
        }

        .footer {
            margin: 18px 0 0;
            color: #8b8799;
            font-size: 0.76rem;
        }

        @media (max-width: 480px) {
            body {
                padding: 16px;
            }

            .card {
                padding: 30px 22px;
            }
        }
    </style>
</head>
<body>
    <main>
        <section class="card">
            <div class="symbol" aria-hidden="true">
                <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.8"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                >
                    <rect x="4" y="5" width="16" height="15" rx="3"></rect>
                    <path d="M8 3v4M16 3v4M4 10h16"></path>
                    <path d="M9 15h6"></path>
                </svg>
            </div>

            <p class="eyebrow">Agenda personal</p>
            <h1>BFGenda está cerrada</h1>

            <p class="description">
                La computadora está conectada, pero la aplicación no se
                encuentra iniciada en este momento.
            </p>

            <div class="notice">
                Para volver a utilizar BFGenda, inicia la aplicación desde
                el acceso directo de la computadora y luego vuelve a cargar
                esta página.
            </div>

            <button
                class="retry"
                type="button"
                onclick="
                    window.scrollTo(0, 0);
                    window.location.replace(
                        window.location.pathname
                        + window.location.search
                    );
                "
            >
                Volver a comprobar
            </button>

            <p class="footer">
                Tu información permanece guardada localmente.
            </p>
        </section>
    </main>
    <script>
        if ("scrollRestoration" in history) {
            history.scrollRestoration = "manual";
        }

        window.scrollTo(0, 0);

        window.addEventListener("pageshow", () => {
            window.scrollTo(0, 0);
        });
    </script>
</body>
</html>
""".encode("utf-8")


class StandbyHandler(BaseHTTPRequestHandler):
    """Entrega la misma página de espera para cualquier ruta."""

    server_version = "BFGenda-Espera"
    sys_version = ""

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGE)))
        self.send_header(
            "Cache-Control",
            "no-store, no-cache, must-revalidate, max-age=0",
        )
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(PAGE)

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGE)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def log_message(self, format_string: str, *args) -> None:
        return


def remove_pid_file() -> None:
    try:
        if not PID_FILE.exists():
            return

        if PID_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
            PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def main() -> int:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    atexit.register(remove_pid_file)

    try:
        server = ThreadingHTTPServer((HOST, PORT), StandbyHandler)
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        remove_pid_file()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

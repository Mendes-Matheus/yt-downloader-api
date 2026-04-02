from pathlib import Path
import tempfile
import random
import os
import base64
from typing import Dict

class DownloadConfig:
    def __init__(self):
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0',
        ]

        self.temp_dir = Path(tempfile.gettempdir()) / "yt_downloader"
        self.temp_dir.mkdir(exist_ok=True)
        self.project_root = Path(__file__).resolve().parents[2]
        self.cookie_file = self._resolve_cookie_file()
        self.js_runtime = (os.getenv("YT_DLP_JS_RUNTIME", "node").strip().lower() or "node")
        self.enable_remote_ejs = os.getenv("YT_DLP_REMOTE_EJS", "1").strip() not in {"0", "false", "False"}
        self.visitor_data = os.getenv("YT_DLP_VISITOR_DATA", "").strip()
        self.player_clients = self._parse_csv_env(
            "YT_DLP_PLAYER_CLIENTS",
            ["ios", "mweb", "tv", "web"],
        )
        self.player_clients_fallback = self._parse_csv_env(
            "YT_DLP_PLAYER_CLIENTS_FALLBACK",
            ["mweb", "tv", "ios", "web"],
        )
        self.player_skip = self._parse_csv_env("YT_DLP_PLAYER_SKIP", ["webpage"])
        self.sleep_interval_requests = self._parse_float_env("YT_DLP_SLEEP_INTERVAL_REQUESTS", 0.0)
        self.max_sleep_interval_requests = self._parse_float_env("YT_DLP_MAX_SLEEP_INTERVAL_REQUESTS", 0.0)
        self.pre_download_sleep_min = self._parse_float_env("YT_DLP_PRE_DOWNLOAD_SLEEP_MIN", 0.0)
        self.pre_download_sleep_max = self._parse_float_env("YT_DLP_PRE_DOWNLOAD_SLEEP_MAX", 0.0)
        self.retry_sleep_min = self._parse_float_env("YT_DLP_RETRY_SLEEP_MIN", 0.2)
        self.retry_sleep_max = self._parse_float_env("YT_DLP_RETRY_SLEEP_MAX", 0.6)
        self.concurrent_fragment_downloads = self._parse_int_env(
            "YT_DLP_CONCURRENT_FRAGMENT_DOWNLOADS",
            4,
            minimum=1,
        )
        self.rate_limit_bytes = self._parse_int_env("YT_DLP_RATELIMIT_BYTES", 0)
        self.throttled_rate_limit_bytes = self._parse_int_env(
            "YT_DLP_THROTTLED_RATELIMIT_BYTES",
            0,
        )

        if self.max_sleep_interval_requests < self.sleep_interval_requests:
            self.max_sleep_interval_requests = self.sleep_interval_requests
        if self.pre_download_sleep_max < self.pre_download_sleep_min:
            self.pre_download_sleep_max = self.pre_download_sleep_min
        if self.retry_sleep_max < self.retry_sleep_min:
            self.retry_sleep_max = self.retry_sleep_min

        # ── Segurança ─────────────────────────────────────────────────────────
        # Token que a Vercel envia em X-Internal-Token
        self.internal_token: str = os.getenv("INTERNAL_API_TOKEN", "").strip()

        # CORS: domínios permitidos, separados por vírgula
        # Ex: ALLOWED_ORIGINS=https://meu-app.vercel.app,https://meudominio.com
        raw_origins = os.getenv("ALLOWED_ORIGINS", "").strip()
        if raw_origins:
            self.allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
        else:
            # Em desenvolvimento, aceita tudo — loga aviso no startup
            self.allowed_origins = ["*"]

    def _parse_csv_env(self, name: str, default: list[str]) -> list[str]:
        raw_value = os.getenv(name, "").strip()
        if not raw_value:
            return default

        values = [item.strip() for item in raw_value.split(",") if item.strip()]
        return values or default

    def _parse_float_env(self, name: str, default: float) -> float:
        raw_value = os.getenv(name, "").strip()
        if not raw_value:
            return default
        try:
            parsed = float(raw_value)
            if parsed < 0:
                return default
            return parsed
        except ValueError:
            return default

    def _parse_int_env(self, name: str, default: int, minimum: int = 0) -> int:
        raw_value = os.getenv(name, "").strip()
        if not raw_value:
            return default
        try:
            parsed = int(raw_value)
            if parsed < minimum:
                return default
            return parsed
        except ValueError:
            return default

    def _resolve_cookie_file(self) -> Path | None:
        cookie_file = os.getenv("YT_DLP_COOKIEFILE")
        inline_cookie_path = self._resolve_inline_cookie_file()

        if cookie_file:
            candidate = Path(cookie_file).expanduser()
            if not candidate.is_absolute():
                candidate = self.project_root / candidate

            if candidate.exists():
                return candidate

            if inline_cookie_path:
                return inline_cookie_path

            return candidate

        if inline_cookie_path:
            return inline_cookie_path

        if not cookie_file:
            docker_cookie_file = Path("/app/cookies.txt")
            if docker_cookie_file.exists():
                return docker_cookie_file
            local_cookie_file = self.project_root / "cookies.txt"
            return local_cookie_file

        return None

    def _resolve_inline_cookie_file(self) -> Path | None:
        cookie_b64 = os.getenv("YT_DLP_COOKIES_B64", "").strip()
        cookie_raw = os.getenv("YT_DLP_COOKIES_RAW", "").strip()
        if not cookie_b64 and not cookie_raw:
            return None

        try:
            if cookie_b64:
                decoded_bytes = base64.b64decode(cookie_b64, validate=True)
                cookie_text = decoded_bytes.decode("utf-8", errors="ignore")
            else:
                # Permite enviar via env com quebras escapadas (\n)
                cookie_text = cookie_raw.replace("\\n", "\n")
        except Exception:
            return None

        if not cookie_text.strip():
            return None

        temp_cookie_file = self.temp_dir / "cookies.from_env.txt"
        temp_cookie_file.parent.mkdir(parents=True, exist_ok=True)
        temp_cookie_file.write_text(cookie_text, encoding="utf-8")
        return temp_cookie_file

    def has_valid_cookie_file(self) -> bool:
        if not self.cookie_file or not self.cookie_file.exists() or self.cookie_file.stat().st_size <= 0:
            return False
        try:
            lines = self.cookie_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            if not lines or lines[0].strip() != "# Netscape HTTP Cookie File":
                return False
            has_youtube_cookie = any(
                ".youtube.com" in line or "youtube.com" in line
                for line in lines
                if line and not line.startswith("#")
            )
            return has_youtube_cookie
        except Exception:
            return False

    def describe_cookie_source(self) -> str:
        if self.cookie_file:
            return f"arquivo de cookies em '{self.cookie_file}'"
        return "nenhuma fonte de cookies configurada"

    def _build_youtube_extractor_args(
        self,
        player_clients: list[str] | None = None,
        player_skip: list[str] | None = None,
    ) -> Dict:
        youtube_args: Dict[str, list[str]] = {
            'player_client': player_clients or self.player_clients,
            'player_skip': player_skip or self.player_skip,
        }
        if self.visitor_data:
            youtube_args['visitor_data'] = [self.visitor_data]
        return {'youtube': youtube_args}

    def get_base_ydl_opts(
        self,
        pasta: Path,
        *,
        player_clients: list[str] | None = None,
        player_skip: list[str] | None = None,
        use_cookies: bool = True,
    ) -> Dict:
        opts = {
            'outtmpl': str(pasta / '%(title)s.%(ext)s'),
            'merge_output_format': 'mp4',
            'noplaylist': True,
            'http_headers': {
                'User-Agent': random.choice(self.user_agents),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
                'Connection': 'keep-alive',
            },
            'socket_timeout': 30,
            'retries': 10,
            'fragment_retries': 10,
            'skip_unavailable_fragments': True,
            'continue_dl': True,
            'extractor_retries': 3,
            'concurrent_fragment_downloads': self.concurrent_fragment_downloads,
            'js_runtimes': {self.js_runtime: {}},
            'extractor_args': self._build_youtube_extractor_args(player_clients, player_skip),
        }

        if self.rate_limit_bytes > 0:
            opts['ratelimit'] = self.rate_limit_bytes

        if self.throttled_rate_limit_bytes > 0:
            opts['throttledratelimit'] = self.throttled_rate_limit_bytes

        if self.sleep_interval_requests > 0 or self.max_sleep_interval_requests > 0:
            opts['sleep_interval_requests'] = self.sleep_interval_requests
            opts['max_sleep_interval_requests'] = self.max_sleep_interval_requests

        if self.enable_remote_ejs:
            opts['remote_components'] = {'ejs:github'}

        if use_cookies and self.has_valid_cookie_file():
            opts['cookiefile'] = str(self.cookie_file)

        return opts

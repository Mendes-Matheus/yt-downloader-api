from pathlib import Path
from typing import Dict, Any
from uuid import uuid4

import yt_dlp

from app.services.download_service import BaseDownloadService

class VideoService(BaseDownloadService):
    def __init__(self):
        super().__init__()
        self.video_temp_dir = self.config.temp_dir / "videos"

    def _normalizar_qualidade_video(self, qualidade: str) -> str:
        quality_value = (qualidade or "720p").strip()
        allowed = {"best", "4K", "1080p", "720p", "480p", "360p"}
        return quality_value if quality_value in allowed else "720p"

    def _get_video_format_selectors(self, qualidade: str) -> list[str]:
        qualidade = self._normalizar_qualidade_video(qualidade)

        strict_format_map = {
            "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
            "4K": "bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/best",
            "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best",
            "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best",
            "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best",
            "360p": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best",
        }
        relaxed_format_map = {
            "best": "bestvideo+bestaudio/best",
            "4K": "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best",
            "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
            "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
            "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]/best",
        }
        progressive_format_map = {
            "best": "22/18/best",
            "4K": "22/18/best",
            "1080p": "22/18/best",
            "720p": "22/18/best",
            "480p": "18/best",
            "360p": "18/best",
        }

        return [
            strict_format_map[qualidade],
            relaxed_format_map[qualidade],
            progressive_format_map[qualidade],
        ]

    def _configurar_opcoes_video(
        self,
        qualidade: str,
        pasta: Path,
        *,
        player_clients: list[str] | None = None,
        use_cookies: bool = True,
        format_selector: str | None = None,
    ) -> Dict:
        """Configura opções para download de vídeo"""
        opcoes = self.config.get_base_ydl_opts(
            pasta,
            player_clients=player_clients,
            use_cookies=use_cookies,
        )
        selectors = self._get_video_format_selectors(qualidade)
        opcoes['format'] = format_selector or selectors[0]
        opcoes['remuxvideo'] = 'mp4'
        return opcoes

    def _is_http_403_error(self, error: Exception) -> bool:
        message = str(error).lower()
        markers = (
            "http error 403",
            "403 forbidden",
            "unable to download video data",
        )
        return any(marker in message for marker in markers)

    def _build_video_attempts(self, qualidade: str) -> list[Dict[str, Any]]:
        format_selectors = self._get_video_format_selectors(qualidade)
        default_clients = self.config.player_clients
        fallback_clients = self.config.player_clients_fallback
        has_cookies = self.config.has_valid_cookie_file()

        attempts = [
            {
                "player_clients": default_clients,
                "use_cookies": True,
                "format_selector": format_selectors[0],
            }
        ]

        if fallback_clients != default_clients:
            attempts.append(
                {
                    "player_clients": fallback_clients,
                    "use_cookies": True,
                    "format_selector": format_selectors[0],
                }
            )

        if has_cookies:
            attempts.append(
                {
                    "player_clients": fallback_clients,
                    "use_cookies": False,
                    "format_selector": format_selectors[0],
                }
            )

        for selector in format_selectors[1:]:
            attempts.append(
                {
                    "player_clients": fallback_clients,
                    "use_cookies": False if has_cookies else True,
                    "format_selector": selector,
                }
            )

        deduped_attempts: list[Dict[str, Any]] = []
        seen: set[tuple[tuple[str, ...], bool, str]] = set()
        for attempt in attempts:
            key = (
                tuple(attempt["player_clients"]),
                attempt["use_cookies"],
                attempt["format_selector"],
            )
            if key in seen:
                continue
            seen.add(key)
            deduped_attempts.append(attempt)

        return deduped_attempts

    def _find_downloaded_video_file(self, temp_basename: str) -> Path | None:
        excluded_suffixes = {".part", ".ytdl", ".temp"}
        candidates = sorted(
            self.video_temp_dir.glob(f"{temp_basename}*"),
            key=lambda path: path.stat().st_mtime if path.exists() else 0,
            reverse=True,
        )
        for candidate in candidates:
            if not candidate.is_file():
                continue
            if any(candidate.name.endswith(suffix) for suffix in excluded_suffixes):
                continue
            return candidate
        return None

    def _cleanup_temp_video_files(self, temp_basename: str) -> None:
        for candidate in self.video_temp_dir.glob(f"{temp_basename}*"):
            if not candidate.is_file():
                continue
            try:
                candidate.unlink()
            except Exception:
                pass

    def baixar_video_temp(self, url: str, qualidade: str = "720p") -> Dict[str, Any]:
        """Baixa vídeo para arquivo temporário"""
        self.video_temp_dir.mkdir(exist_ok=True)

        temp_basename = f"temp_{uuid4().hex}"
        attempts = self._build_video_attempts(qualidade)
        last_error: Exception | None = None

        self.aguardar_inicio_download()

        for attempt_index, attempt in enumerate(attempts):
            opcoes = self._configurar_opcoes_video(
                qualidade,
                self.video_temp_dir,
                player_clients=attempt["player_clients"],
                use_cookies=attempt["use_cookies"],
                format_selector=attempt["format_selector"],
            )
            opcoes['outtmpl'] = str(self.video_temp_dir / f"{temp_basename}.%(ext)s")

            try:
                with yt_dlp.YoutubeDL(opcoes) as ydl:
                    info = ydl.extract_info(url, download=True)

                downloaded_file = self._find_downloaded_video_file(temp_basename)
                if not downloaded_file:
                    raise Exception("Arquivo temporario de video nao foi criado")

                final_ext = downloaded_file.suffix or ".mp4"
                final_filename = f"{self.file_utils.sanitize_filename(info['title'])}{final_ext}"
                final_filepath = self.video_temp_dir / final_filename

                try:
                    downloaded_file.rename(final_filepath)
                except Exception:
                    final_filepath = downloaded_file
                    final_filename = downloaded_file.name

                if not final_filepath.exists():
                    raise Exception(f"Arquivo final nao existe: {final_filepath}")

                file_size = final_filepath.stat().st_size

                return {
                    'status': 'sucesso',
                    'filepath': str(final_filepath),
                    'filename': final_filename,
                    'titulo': info['title'],
                    'tamanho': file_size
                }

            except Exception as error:
                last_error = error
                self._cleanup_temp_video_files(temp_basename)

                has_next_attempt = attempt_index < (len(attempts) - 1)
                if has_next_attempt and self._is_http_403_error(error):
                    self.aguardar_retry_download()
                    continue
                break

        if last_error:
            raise Exception(f"Erro no download: {self.formatar_erro_download(last_error)}")
        raise Exception("Erro no download: falha inesperada durante o download de video.")

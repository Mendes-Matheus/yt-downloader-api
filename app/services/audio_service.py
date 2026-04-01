import time
import random
from pathlib import Path
from typing import Dict, Any

import yt_dlp

from app.services.download_service import BaseDownloadService

class AudioService(BaseDownloadService):
    def __init__(self):
        super().__init__()
        self.audio_temp_dir = self.config.temp_dir / "audios"

    def _normalizar_qualidade_audio(self, qualidade_audio: str) -> str:
        quality_map = {
            "320kbps": "320",
            "256kbps": "256",
            "192kbps": "192",
            "128kbps": "128",
            "64kbps": "64",
        }
        allowed_values = {"320", "256", "192", "128", "64"}

        quality_value = (qualidade_audio or "192").strip().lower()
        if quality_value in quality_map:
            return quality_map[quality_value]
        if quality_value in allowed_values:
            return quality_value
        return "192"

    def _configurar_opcoes_audio(
        self,
        pasta: Path,
        qualidade_audio: str = "192",
        *,
        player_clients: list[str] | None = None,
        use_cookies: bool = True,
        format_selector: str = "bestaudio/best",
    ) -> Dict:
        """Configura opções para download de áudio"""
        bitrate = self._normalizar_qualidade_audio(qualidade_audio)
        opcoes = self.config.get_base_ydl_opts(
            pasta,
            player_clients=player_clients,
            use_cookies=use_cookies,
        )
        opcoes.update({
            'format': format_selector,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': bitrate,
            }],
        })
        return opcoes

    def _is_http_403_error(self, error: Exception) -> bool:
        message = str(error).lower()
        markers = (
            "http error 403",
            "403 forbidden",
            "unable to download video data",
        )
        return any(marker in message for marker in markers)

    def _build_audio_attempts(self) -> list[Dict[str, Any]]:
        default_clients = self.config.player_clients
        fallback_clients = self.config.player_clients_fallback
        has_cookies = self.config.has_valid_cookie_file()

        attempts = [
            {
                "player_clients": default_clients,
                "use_cookies": True,
                "format_selector": "bestaudio/best",
            }
        ]

        if fallback_clients != default_clients:
            attempts.append(
                {
                    "player_clients": fallback_clients,
                    "use_cookies": True,
                    "format_selector": "bestaudio/best",
                }
            )

        if has_cookies:
            attempts.append(
                {
                    "player_clients": fallback_clients,
                    "use_cookies": False,
                    "format_selector": "bestaudio/best",
                }
            )

        attempts.append(
            {
                "player_clients": fallback_clients,
                "use_cookies": False if has_cookies else True,
                "format_selector": "18/bestaudio/best",
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

    def baixar_audio_temp(self, url: str, qualidade_audio: str = "192") -> Dict[str, Any]:
        """Baixa áudio para arquivo temporário"""
        self.audio_temp_dir.mkdir(exist_ok=True)

        temp_basename = f"temp_{int(time.time())}"
        temp_mp3_path = self.audio_temp_dir / f"{temp_basename}.mp3"
        last_error: Exception | None = None
        attempts = self._build_audio_attempts()

        time.sleep(random.uniform(1, 2))

        for attempt_index, attempt in enumerate(attempts):
            opcoes = self._configurar_opcoes_audio(
                self.audio_temp_dir,
                qualidade_audio,
                player_clients=attempt["player_clients"],
                use_cookies=attempt["use_cookies"],
                format_selector=attempt["format_selector"],
            )
            opcoes['outtmpl'] = str(self.audio_temp_dir / f"{temp_basename}.%(ext)s")

            try:
                with yt_dlp.YoutubeDL(opcoes) as ydl:
                    info = ydl.extract_info(url, download=True)

                if not temp_mp3_path.exists():
                    raise Exception("Arquivo MP3 temporario nao foi criado")

                final_filename = f"{self.file_utils.sanitize_filename(info['title'])}.mp3"
                final_filepath = self.audio_temp_dir / final_filename

                try:
                    temp_mp3_path.rename(final_filepath)
                except Exception:
                    final_filepath = temp_mp3_path
                    final_filename = temp_mp3_path.name

                if not final_filepath.exists():
                    raise Exception(f"Arquivo final nao existe: {final_filepath}")

                return {
                    'status': 'sucesso',
                    'filepath': str(final_filepath),
                    'filename': final_filename,
                    'titulo': info['title'],
                    'tamanho': final_filepath.stat().st_size
                }
            except Exception as error:
                last_error = error
                if temp_mp3_path.exists():
                    try:
                        temp_mp3_path.unlink()
                    except Exception:
                        pass

                has_next_attempt = attempt_index < (len(attempts) - 1)
                if has_next_attempt and self._is_http_403_error(error):
                    time.sleep(random.uniform(0.4, 1.2))
                    continue
                break

        if last_error:
            raise Exception(f"Erro no download: {self.formatar_erro_download(last_error)}")
        raise Exception("Erro no download: falha inesperada durante o download de áudio.")

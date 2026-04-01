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

    def _configurar_opcoes_audio(self, pasta: Path, qualidade_audio: str = "192") -> Dict:
        """Configura opções para download de áudio"""
        bitrate = self._normalizar_qualidade_audio(qualidade_audio)
        opcoes = self.config.get_base_ydl_opts(pasta)
        opcoes.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': bitrate,
            }],
        })
        return opcoes

    def baixar_audio_temp(self, url: str, qualidade_audio: str = "192") -> Dict[str, Any]:
        """Baixa áudio para arquivo temporário"""
        self.audio_temp_dir.mkdir(exist_ok=True)

        temp_basename = f"temp_{int(time.time())}"
        temp_mp3_path = self.audio_temp_dir / f"{temp_basename}.mp3"

        opcoes = self._configurar_opcoes_audio(self.audio_temp_dir, qualidade_audio)
        opcoes['outtmpl'] = str(self.audio_temp_dir / f"{temp_basename}.%(ext)s")
        
        try:
            time.sleep(random.uniform(1, 3))
            
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
        except Exception as e:
            if temp_mp3_path.exists():
                try:
                    temp_mp3_path.unlink()
                except Exception:
                    pass
            raise Exception(f"Erro no download: {self.formatar_erro_download(e)}")

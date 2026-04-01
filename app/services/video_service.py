import time
from pathlib import Path
from typing import Dict, Any

import yt_dlp

from app.services.download_service import BaseDownloadService

class VideoService(BaseDownloadService):
    def __init__(self):
        super().__init__()
        self.video_temp_dir = self.config.temp_dir / "videos"

    def _configurar_opcoes_video(self, qualidade: str, pasta: Path) -> Dict:
        """Configura opções para download de vídeo"""
        opcoes = self.config.get_base_ydl_opts(pasta)
        
        format_map = {
            "best": 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
            "4K": 'bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/best',
            "1080p": 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best',
            "720p": 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best',
            "480p": 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best',
            "360p": 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best'
        }

        opcoes['format'] = format_map.get(qualidade, qualidade)
        return opcoes

    def baixar_video_temp(self, url: str, qualidade: str = "720p") -> Dict[str, Any]:
        """Baixa vídeo para arquivo temporário"""
        self.video_temp_dir.mkdir(exist_ok=True)
        
        temp_filename = f"temp_{int(time.time())}.mp4"
        temp_filepath = self.video_temp_dir / temp_filename
        
        opcoes = self._configurar_opcoes_video(qualidade, self.video_temp_dir)
        opcoes['outtmpl'] = str(temp_filepath)
        
        try:
            with yt_dlp.YoutubeDL(opcoes) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if not temp_filepath.exists():
                    raise Exception("Arquivo temporário não foi criado")
                
                final_filename = f"{self.file_utils.sanitize_filename(info['title'])}.mp4"
                final_filepath = self.video_temp_dir / final_filename
                
                try:
                    temp_filepath.rename(final_filepath)
                except Exception:
                    final_filepath = temp_filepath
                    final_filename = temp_filename
                
                if not final_filepath.exists():
                    raise Exception(f"Arquivo final não existe: {final_filepath}")
                
                file_size = final_filepath.stat().st_size
                
                return {
                    'status': 'sucesso',
                    'filepath': str(final_filepath),
                    'filename': final_filename,
                    'titulo': info['title'],
                    'tamanho': file_size
                }
                
        except Exception as e:
            if temp_filepath.exists():
                try:
                    temp_filepath.unlink()
                except:
                    pass
            raise Exception(f"Erro no download: {self.formatar_erro_download(e)}")

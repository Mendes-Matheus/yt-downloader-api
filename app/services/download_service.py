import yt_dlp
from pathlib import Path
from typing import Dict, Any, Optional

from app.utils.config_utils import DownloadConfig
from app.utils.file_utils import FileUtils

class BaseDownloadService:
    def __init__(self):
        self.config = DownloadConfig()
        self.file_utils = FileUtils()

    def formatar_erro_download(self, error: Exception) -> str:
        message = str(error)
        message_lower = message.lower()

        bot_protection_markers = (
            "sign in to confirm you're not a bot",
            "use --cookies-from-browser or --cookies",
        )
        invalid_cookie_markers = (
            "does not look like a netscape format cookies file",
            "invalid cookie",
        )

        if any(marker in message_lower for marker in bot_protection_markers):
            if self.config.has_valid_cookie_file():
                return (
                    "O YouTube exigiu autenticacao para liberar este video. "
                    f"O app ja tentou usar {self.config.describe_cookie_source()}, "
                    "mas a autenticacao falhou. Atualize o arquivo de cookies com o script "
                    "'./update_cookies.sh' e tente novamente."
                )

            return (
                "O YouTube exigiu autenticacao para liberar este video. "
                "Nao foi encontrado cookie valido de youtube.com em '/app/cookies.txt'. "
                "Gere o arquivo de cookies na raiz do projeto com './update_cookies.sh' "
                "ou configure YT_DLP_COOKIEFILE apontando para um arquivo Netscape valido."
            )

        if any(marker in message_lower for marker in invalid_cookie_markers):
            return (
                "O arquivo de cookies nao esta em formato Netscape valido. "
                "Execute './update_cookies.sh' para regenerar '/app/cookies.txt' e reinicie o container."
            )

        return message

    def obter_info_video(self, url: str) -> Optional[Dict[str, Any]]:
        """Obtém metadados do vídeo"""
        try:
            opts = {
                'quiet': True,
                'no_warnings': False,
                'ignoreerrors': True,
                'extract_flat': False,
            }
            opts.update(self.config.get_base_ydl_opts(Path(".")))
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    'titulo': info.get('title', 'N/A'),
                    'duracao': info.get('duration', 0),
                    'canal': info.get('uploader', 'N/A'),
                    'visualizacoes': info.get('view_count', 0),
                    'data_upload': info.get('upload_date', 'N/A'),
                    'thumbnail': info.get('thumbnail', 'N/A'),
                    'descricao': info.get('description', '')[:500] + '...' if info.get('description') else 'N/A'
                }
        except Exception as e:
            raise Exception(f"Erro ao obter informações: {self.formatar_erro_download(e)}")

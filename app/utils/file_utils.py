import time
from pathlib import Path
from typing import Optional

class FileUtils:
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Remove caracteres problemáticos do nome do arquivo"""
        if not filename or filename.strip() == "":
            return "video_sem_titulo"
        
        problematic_chars = [
            '<', '>', ':', '"', '/', '\\', '|', '?', '*',
            '‘', '’', '“', '”', '`', '⧸', '∕', '⁄', '¬', '¦',
            '…', '–', '—', '~', '^', '\n', '\r', '\t',
            '#', '%', '&', '{', '}', '$', '!', '@', '+', '=', '[', ']', ';',
        ]
        
        for char in problematic_chars:
            filename = filename.replace(char, '_')
        
        filename = filename.replace('/', '_').replace('\\', '_')
        filename = ' '.join(filename.split()).strip()
        
        if not filename:
            filename = "video_sem_titulo"
        
        filename = filename.strip('. ')
        
        if len(filename) > 150:
            filename = filename[:147] + "..."
        
        return filename

    @staticmethod
    def limpar_arquivos_temp(temp_dir: Path, idade_maxima_minutos: int = 60):
        """Limpa arquivos temporários antigos"""
        agora = time.time()
        for arquivo in temp_dir.rglob('*'):
            if arquivo.is_file():
                if (agora - arquivo.stat().st_mtime) > (idade_maxima_minutos * 60):
                    arquivo.unlink()
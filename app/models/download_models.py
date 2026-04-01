from pydantic import BaseModel
from typing import Optional, Dict, Any

class DownloadRequest(BaseModel):
    url: str
    qualidade: str = "720p"

class AudioRequest(BaseModel):
    url: str
    qualidade_audio: str = "192"

class DownloadResult(BaseModel):
    status: str
    filepath: str
    filename: str
    titulo: str
    tamanho: int

class VideoInfo(BaseModel):
    titulo: str
    duracao: int
    canal: str
    visualizacoes: int
    data_upload: str
    thumbnail: str
    descricao: str

from pydantic import BaseModel

class DownloadRequest(BaseModel):
    url: str
    qualidade: str = "720p"

class AudioRequest(BaseModel):
    url: str
    qualidade_audio: str = "192"


class AudioEnqueueResponse(BaseModel):
    task_id: str
    status: str
    status_url: str
    download_url: str


class AudioStatusResponse(BaseModel):
    task_id: str
    status: str
    stage: str
    ready: bool
    error: str | None = None
    filename: str | None = None
    titulo: str | None = None
    tamanho: int | None = None

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

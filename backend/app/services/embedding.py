import logging

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


# Lazy LangChain HuggingFaceEmbeddings wrapper -- model loads on first use so
# tests that monkeypatch embed_texts never pay the download/load cost.
class _LocalEmbedder:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from langchain_community.embeddings import HuggingFaceEmbeddings
            logger.info("loading local embedding model name=%s", self.model_name)
            self._model = HuggingFaceEmbeddings(model_name=self.model_name)
        return self._model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._load().embed_documents(texts)


embedder = _LocalEmbedder(EMBEDDING_MODEL)

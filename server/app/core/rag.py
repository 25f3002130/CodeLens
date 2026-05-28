import chromadb
from chromadb.utils import embedding_functions
from typing import List, Dict, Any

class RAGEngine:
    def __init__(self, persist_directory: str = "./chroma_db"):
        self.persist_directory = persist_directory
        self.client = None
        self.collection = None
        self.disabled = False
        self.disabled_reason = ""

    def _ensure_collection(self):
        if self.disabled:
            raise RuntimeError(self.disabled_reason or "RAG is disabled")

        if self.collection is not None:
            return self.collection

        try:
            client = chromadb.PersistentClient(path=self.persist_directory)
            embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
            self.client = client
            self.collection = client.get_or_create_collection(
                name="codelens_chunks",
                embedding_function=embedding_fn,
            )
            return self.collection
        except Exception as e:
            self.disabled = True
            self.disabled_reason = f"RAG initialization failed: {e}"
            print(f"Warning: {self.disabled_reason}")
            raise

    def index_repo(self, repo_id: str, files: List[Dict[str, Any]]):
        """
        Chunks and indexes the code files for a specific repository.
        """
        documents = []
        metadatas = []
        ids = []

        for file in files:
            content = file.get("content", "")
            if not content:
                continue

            chunks = self._chunk_code(content, chunk_size=1000)

            for i, chunk in enumerate(chunks):
                documents.append(chunk)
                metadatas.append({
                    "repo_id": repo_id,
                    "file_path": file["file_path"],
                    "language": file["language"],
                    "chunk_index": i,
                })
                ids.append(f"{repo_id}_{file['file_path']}_{i}")

        if not documents or self.disabled:
            return

        try:
            self._ensure_collection().upsert(
                documents=documents,
                metadatas=metadatas,
                ids=ids,
            )
        except Exception as e:
            self.disabled = True
            self.disabled_reason = f"RAG indexing failed: {e}"
            print(f"Warning: {self.disabled_reason}")

    def _chunk_code(self, content: str, chunk_size: int) -> List[str]:
        lines = content.split("\n")
        chunks = []
        current_chunk = []
        current_size = 0

        for line in lines:
            if current_size + len(line) > chunk_size and current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_size = 0

            current_chunk.append(line)
            current_size += len(line)

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        return chunks

    def query(self, repo_id: str, query_text: str, n_results: int = 5) -> Dict[str, Any]:
        if self.disabled:
            return {"documents": [[]], "metadatas": [[]], "ids": [[]]}

        try:
            return self._ensure_collection().query(
                query_texts=[query_text],
                n_results=n_results,
                where={"repo_id": repo_id},
            )
        except Exception as e:
            self.disabled = True
            self.disabled_reason = f"RAG query failed: {e}"
            print(f"Warning: {self.disabled_reason}")
            return {"documents": [[]], "metadatas": [[]], "ids": [[]]}

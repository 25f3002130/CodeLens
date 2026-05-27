import os
import git
import shutil
import hashlib
import tempfile
from urllib.parse import urlparse

class IngestionEngine:
    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = os.path.join(tempfile.gettempdir(), "codelens_repos")
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def _get_repo_path(self, repo_url: str) -> str:
        # Create a unique directory name based on the URL hash
        url_hash = hashlib.sha256(repo_url.encode()).hexdigest()[:12]
        repo_name = repo_url.split("/")[-1].replace(".git", "") or "repo"
        return os.path.join(self.base_dir, f"{repo_name}_{url_hash}")

    def _validate_repo_url(self, repo_url: str):
        parsed = urlparse(repo_url)
        if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
            raise ValueError("Only https://github.com repositories are supported.")

        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            raise ValueError("Repository URL must include an owner and repository name.")

    def clone_repo(self, repo_url: str) -> str:
        self._validate_repo_url(repo_url)
        target_path = tempfile.mkdtemp(prefix=f"{hashlib.sha256(repo_url.encode()).hexdigest()[:12]}_", dir=self.base_dir)
        print(f"Cloning {repo_url} to temporary directory {target_path}...")
        git.Repo.clone_from(repo_url, target_path, depth=1)

        return target_path

    def cleanup(self, repo_path: str):
        if os.path.exists(repo_path):
            shutil.rmtree(repo_path)
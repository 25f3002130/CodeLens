import os
from typing import List, Dict, Any
from .ingestion import IngestionEngine
from .ai_analyzer import AIAnalyzer
import hashlib

class CodeAnalyzer:
    SKIP_DIRS = {".git", "node_modules", "__pycache__", ".next", "dist", "build", "coverage", "venv", ".venv"}
    MAX_FILES = 250
    MAX_FILE_BYTES = 200_000
    ALLOWED_EXTS = {"py", "js", "jsx", "ts", "tsx", "java", "go", "rs", "php", "rb", "cs", "cpp", "c", "h", "hpp"}

    def __init__(self):
        self.ingestion = IngestionEngine()
        self.enable_ai_analysis = os.getenv("CODELENS_ENABLE_AI_ANALYSIS", "true").lower() in {"1", "true", "yes", "on"}
        self.max_files = int(os.getenv("CODELENS_MAX_FILES", str(self.MAX_FILES)))
        self.max_file_bytes = int(os.getenv("CODELENS_MAX_FILE_BYTES", str(self.MAX_FILE_BYTES)))
        # Initialize AI Analyzer
        if self.enable_ai_analysis:
            try:
                self.ai_analyzer = AIAnalyzer()
            except ValueError as e:
                print(f"Warning: AI Analyzer not available - {e}")
                self.ai_analyzer = None
        else:
            self.ai_analyzer = None

    def analyze_repo(self, repo_url: str, progress_callback=None) -> Dict[str, Any]:
        repo_path = None
        repo_id = hashlib.sha256(repo_url.encode()).hexdigest()[:12]
        all_files = []
        try:
            repo_path = self.ingestion.clone_repo(repo_url)
            if progress_callback:
                progress_callback("Clone complete. Starting AI analysis...")

            for root, dirs, files in os.walk(repo_path):
                dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]

                for file in files:
                    if len(all_files) >= self.max_files:
                        break

                    ext = file.rsplit(".", 1)[-1].lower()
                    if ext in self.ALLOWED_EXTS:
                        file_path = os.path.join(root, file)
                        relative_path = os.path.relpath(file_path, repo_path)

                        try:
                            if os.path.getsize(file_path) > self.max_file_bytes:
                                continue

                            with open(file_path, "r", errors="ignore") as f:
                                content = f.read()

                            language_map = {
                                "py": "python",
                                "js": "javascript",
                                "jsx": "javascript",
                                "ts": "typescript",
                                "tsx": "typescript",
                            }

                            all_files.append({
                                "file_path": relative_path,
                                "language": language_map.get(ext, ext),
                                "content": content,
                                "complexity": 0,
                                "functions": [],
                                "classes": [],
                                "vulnerabilities": [],
                            })
                        except Exception as e:
                            print(f"Error parsing {file_path}: {e}")

            graph_data = {"nodes": [], "links": []}
            vulnerabilities = []
            hotspots = []

            ai_tech_stack = {}
            ai_deps_data = {}

            # Use AI Analysis to enhance findings if available
            if self.ai_analyzer:
                try:
                    print("Running AI analysis with NVIDIA NIM API...")
                    if progress_callback:
                        self.ai_analyzer.set_progress_callback(progress_callback)
                    ai_results = self.ai_analyzer.analyze_codebase(all_files)
                    # AI is the single source for analysis output
                    ai_vulns = ai_results.get("vulnerabilities", [])
                    if ai_vulns and isinstance(ai_vulns, list):
                        vulnerabilities = self._deduplicate_vulnerabilities(ai_vulns)
                        msg = f"AI analysis added {len(ai_vulns)} vulnerabilities"
                        print(msg)
                        if progress_callback:
                            progress_callback(f"✅ {msg}")

                    # AI hotspots only
                    ai_hotspots = ai_results.get("hotspots", [])
                    if ai_hotspots and isinstance(ai_hotspots, list):
                        hotspots = sorted(ai_hotspots, key=lambda x: x.get("complexity", 0), reverse=True)[:10]
                        msg = f"AI analysis added {len(ai_hotspots)} hotspots"
                        print(msg)
                        if progress_callback:
                            progress_callback(f"✅ {msg}")

                    # Extract LLM tech stack and dependencies
                    ai_tech_stack = ai_results.get("tech_stack", {})
                    ai_deps_data = ai_results.get("dependencies", {})

                except Exception as e:
                    print(f"AI analysis failed, continuing with basic analysis: {e}")

            # Remove content from API response to keep payload lightweight.
            for f in all_files:
                if "content" in f:
                    del f["content"]

            dependency_manifests = []
            dependency_count = 0

            return {
                "repo_id": repo_id,
                "repo_url": repo_url,
                "files": all_files,
                "graph": graph_data,
                "hotspots": hotspots,
                "vulnerabilities": vulnerabilities,
                "dependency_manifests": dependency_manifests,
                "tech_stack": ai_tech_stack,
                "ai_dependencies": ai_deps_data,
                "stats": {
                    "total_files": len(all_files),
                    "languages": self._count_languages(all_files),
                    "total_vulnerabilities": len(vulnerabilities),
                    "critical_vulnerabilities": sum(1 for item in vulnerabilities if item.get("severity") == "CRITICAL"),
                    "high_vulnerabilities": sum(1 for item in vulnerabilities if item.get("severity") == "HIGH"),
                    "hotspot_count": len(hotspots),
                    "graph_links": len(graph_data["links"]),
                    "dependency_manifests": len(dependency_manifests),
                    "dependencies": dependency_count,
                }
            }
        finally:
            if repo_path:
                self.ingestion.cleanup(repo_path)

    def _count_languages(self, files: List[Dict]) -> Dict[str, int]:
        counts = {}
        for f in files:
            lang = f["language"]
            counts[lang] = counts.get(lang, 0) + 1
        return counts

    def _deduplicate_vulnerabilities(self, vulnerabilities: List[Dict]) -> List[Dict]:
        """Deduplicate vulnerabilities while preserving all unique findings."""
        seen = set()
        unique = []
        for vuln in vulnerabilities:
            # Safely extract values, converting to strings if needed
            name = str(vuln.get("name", ""))
            file_path = str(vuln.get("file_path", ""))
            line = str(vuln.get("line", 0))
            # Create a key from name, file_path, and line to avoid duplicates
            key = (name, file_path, line)
            if key not in seen:
                seen.add(key)
                unique.append(vuln)
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        return sorted(unique, key=lambda item: (severity_order.get(str(item.get("severity", "LOW")), 9), str(item.get("file_path", "")), int(item.get("line", 0))))

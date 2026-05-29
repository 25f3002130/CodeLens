import os
import re
import json
from typing import List, Dict, Any
from .ingestion import IngestionEngine
from .ai_analyzer import AIAnalyzer
from .graph import GraphBuilder
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

                            imports = self._extract_imports(content, ext)

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
                                "imports": imports,
                                "vulnerabilities": [],
                            })
                        except Exception as e:
                            print(f"Error parsing {file_path}: {e}")

            vulnerabilities = []
            hotspots = []

            graph_data = {"nodes": [], "links": []}
            ai_tech_stack = {}
            ai_deps_data = {}
            repo_context_files = self._collect_repo_context_files(all_files)

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

                    if not isinstance(ai_deps_data, dict):
                        ai_deps_data = self._normalize_dependency_payload(ai_deps_data)

                    graph_data = GraphBuilder(repo_path, all_files).build_graph()

                except Exception as e:
                    print(f"AI analysis failed, continuing with basic analysis: {e}")

            # Remove content from API response to keep payload lightweight.
            for f in all_files:
                if "content" in f:
                    del f["content"]

            dependency_manifests = []
            dependency_count = 0

            snapshot = {
                "repo_id": repo_id,
                "repo_url": repo_url,
                "repo_path": repo_path,
                "files": [
                    {
                        "file_path": f.get("file_path"),
                        "language": f.get("language"),
                        "imports": f.get("imports", []),
                        "complexity": f.get("complexity", 0),
                        "functions": f.get("functions", []),
                        "classes": f.get("classes", []),
                        "vulnerabilities": len(f.get("vulnerabilities", [])),
                    }
                    for f in all_files
                ],
                "special_files": repo_context_files,
                "graph": graph_data,
                "hotspots": hotspots,
                "vulnerabilities": vulnerabilities,
                "tech_stack": ai_tech_stack,
                "ai_dependencies": ai_deps_data,
            }
            self.ingestion.save_snapshot(repo_id, snapshot)

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
                # Keep the cloned repo for chat queries; cleanups can be scheduled separately.
                pass

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            try:
                import re
                match = re.search(r"(\d+)", str(value))
                if match:
                    return int(match.group(1))
            except Exception:
                pass
        return default

    def _extract_imports(self, content: str, ext: str) -> List[str]:
        imports = []
        if ext == "py":
            for match in re.finditer(r"^\s*(?:from\s+([\w\.]+)\s+import|import\s+([\w\.]+))", content, re.MULTILINE):
                imports.extend([group for group in match.groups() if group])
        elif ext in {"js", "jsx", "ts", "tsx"}:
            patterns = [
                r"import\s+.*?from\s+['\"]([^'\"]+)['\"]",
                r"require\(\s*['\"]([^'\"]+)['\"]\s*\)",
            ]
            for pattern in patterns:
                imports.extend(re.findall(pattern, content))
        return list(dict.fromkeys(imports))

    def _collect_repo_context_files(self, files: List[Dict]) -> List[Dict[str, Any]]:
        context_files = []
        priority_names = {"README.md", "README", "package.json", "pyproject.toml", "requirements.txt", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"}

        for file in files:
            file_path = str(file.get("file_path", ""))
            basename = os.path.basename(file_path)
            if basename not in priority_names:
                continue

            content = str(file.get("content", ""))
            context_files.append({
                "file_path": file_path,
                "language": file.get("language", "text"),
                "content": content[:4000],
            })

        return context_files

    def _normalize_dependency_payload(self, dependencies: Any) -> Dict[str, List[Dict]]:
        """Normalize loose dependency payloads into the shape expected by the frontend."""
        normalized = {"vulnerable": [], "outdated": []}

        if isinstance(dependencies, list):
            for item in dependencies:
                if isinstance(item, dict) and item.get("name"):
                    normalized["vulnerable"].append(item)
            return normalized

        if not isinstance(dependencies, dict):
            return normalized

        for key in ("vulnerable", "vulnerabilities", "security", "security_risks"):
            items = dependencies.get(key, [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and item.get("name"):
                        normalized["vulnerable"].append(item)

        for key in ("outdated", "updates", "outdated_packages"):
            items = dependencies.get(key, [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and item.get("name"):
                        normalized["outdated"].append(item)

        if isinstance(dependencies.get("vulnerable"), list):
            normalized["vulnerable"] = dependencies.get("vulnerable", [])
        if isinstance(dependencies.get("outdated"), list):
            normalized["outdated"] = dependencies.get("outdated", [])

        return normalized

    def _build_graph_data(self, files: List[Dict], vulnerabilities: List[Dict], hotspots: List[Dict]) -> Dict[str, Any]:
        """Build a lightweight file graph for the 3D visualization."""
        vuln_map = {}
        hotspot_set = set()

        for vuln in vulnerabilities:
            path = str(vuln.get("file_path", ""))
            vuln_map[path] = vuln_map.get(path, 0) + 1

        for hotspot in hotspots:
            path = str(hotspot.get("file_path", ""))
            if path:
                hotspot_set.add(path)

        nodes = []
        links = []
        seen_dirs = set()

        for file in files[:200]:
            file_path = str(file.get("file_path", ""))
            if not file_path:
                continue

            language = str(file.get("language", "unknown"))
            complexity = self._safe_int(file.get("complexity", 0), 0)
            vuln_count = vuln_map.get(file_path, 0)
            is_hotspot = file_path in hotspot_set
            parts = file_path.split("/")
            parent = "/".join(parts[:-1]) if len(parts) > 1 else ""
            node_id = file_path

            nodes.append({
                "id": node_id,
                "name": parts[-1],
                "path": file_path,
                "language": language,
                "complexity": complexity,
                "vulnerabilities": vuln_count,
                "val": max(2, min(18, 2 + complexity + vuln_count * 3 + (3 if is_hotspot else 0))),
            })

            if parent:
                parent_id = parent
                if parent_id not in seen_dirs:
                    seen_dirs.add(parent_id)
                    nodes.append({
                        "id": parent_id,
                        "name": parts[-2],
                        "path": parent_id,
                        "language": "folder",
                        "complexity": 0,
                        "vulnerabilities": 0,
                        "val": 3,
                        "isFolder": True,
                    })
                links.append({"source": parent_id, "target": node_id})

        return {"nodes": nodes, "links": links}

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

        def safe_int(val, default=0):
            try:
                return int(val)
            except Exception:
                try:
                    s = str(val)
                    import re
                    m = re.search(r"(\d+)", s)
                    if m:
                        return int(m.group(1))
                except Exception:
                    pass
            return default

        return sorted(unique, key=lambda item: (severity_order.get(str(item.get("severity", "LOW")), 9), str(item.get("file_path", "")), safe_int(item.get("line", 0))))

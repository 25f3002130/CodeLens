import os
from typing import List, Dict, Any
from .ingestion import IngestionEngine
from .parser import CodeParser
from .graph import GraphBuilder
from .security import SecurityScanner
from .rag import RAGEngine
from .ai_analyzer import AIAnalyzer
import hashlib
import json

class CodeAnalyzer:
    SKIP_DIRS = {".git", "node_modules", "__pycache__", ".next", "dist", "build", "coverage", "venv", ".venv"}
    MAX_FILES = 750
    MAX_FILE_BYTES = 500_000

    def __init__(self):
        self.ingestion = IngestionEngine()
        self.security = SecurityScanner()
        self.rag = RAGEngine()
        self.parsers = {
            "py": CodeParser("python"),
            "js": CodeParser("javascript"),
            "jsx": CodeParser("javascript"),
            "ts": CodeParser("typescript"),
            "tsx": CodeParser("tsx"),
        }
        # Initialize AI Analyzer
        try:
            self.ai_analyzer = AIAnalyzer()
        except ValueError as e:
            print(f"Warning: AI Analyzer not available - {e}")
            self.ai_analyzer = None

    def analyze_repo(self, repo_url: str, progress_callback=None) -> Dict[str, Any]:
        repo_path = None
        repo_id = hashlib.sha256(repo_url.encode()).hexdigest()[:12]
        all_files = []
        try:
            repo_path = self.ingestion.clone_repo(repo_url)

            for root, dirs, files in os.walk(repo_path):
                dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]

                for file in files:
                    if len(all_files) >= self.MAX_FILES:
                        break

                    ext = file.rsplit(".", 1)[-1].lower()
                    if ext in self.parsers:
                        file_path = os.path.join(root, file)
                        relative_path = os.path.relpath(file_path, repo_path)

                        try:
                            if os.path.getsize(file_path) > self.MAX_FILE_BYTES:
                                continue

                            with open(file_path, "r", errors="ignore") as f:
                                content = f.read()

                            analysis = self.parsers[ext].parse_file(file_path)
                            analysis["file_path"] = relative_path
                            analysis["content"] = content # Needed for indexing
                            analysis["vulnerabilities"] = self.security.scan_file(file_path, content)

                            all_files.append(analysis)
                        except Exception as e:
                            print(f"Error parsing {file_path}: {e}")

            # Build Graph
            graph_gen = GraphBuilder(repo_path, all_files)
            graph_data = graph_gen.build_graph()

            # Index for RAG
            self.rag.index_repo(repo_id, all_files)

            # Remove content from response to keep it light
            for f in all_files:
                if "content" in f:
                    del f["content"]

            # Get vulnerabilities and hotspots
            vulnerabilities = self._collect_vulnerabilities(all_files)
            hotspots = self._calculate_hotspots(all_files)

            ai_tech_stack = {}
            ai_deps_data = {}

            # Use AI Analysis to enhance findings if available
            if self.ai_analyzer:
                try:
                    print("Running AI analysis with NVIDIA NIM API...")
                    if progress_callback:
                        self.ai_analyzer.set_progress_callback(progress_callback)
                    ai_results = self.ai_analyzer.analyze_codebase(all_files)
                    # Merge AI-detected vulnerabilities with existing ones
                    ai_vulns = ai_results.get("vulnerabilities", [])
                    if ai_vulns and isinstance(ai_vulns, list):
                        vulnerabilities.extend(ai_vulns)
                        vulnerabilities = self._deduplicate_vulnerabilities(vulnerabilities)
                        msg = f"AI analysis added {len(ai_vulns)} vulnerabilities"
                        print(msg)
                        if progress_callback:
                            progress_callback(f"✅ {msg}")

                    # Merge AI-detected hotspots
                    ai_hotspots = ai_results.get("hotspots", [])
                    if ai_hotspots and isinstance(ai_hotspots, list):
                        hotspots.extend(ai_hotspots)
                        hotspots = sorted(hotspots, key=lambda x: x.get("complexity", 0), reverse=True)[:10]
                        msg = f"AI analysis added {len(ai_hotspots)} hotspots"
                        print(msg)
                        if progress_callback:
                            progress_callback(f"✅ {msg}")

                    # Extract LLM tech stack and dependencies
                    ai_tech_stack = ai_results.get("tech_stack", {})
                    ai_deps_data = ai_results.get("dependencies", {})

                    # Build a list of external dependency nodes from LLM
                    llm_deps = []
                    for fw in ai_tech_stack.get("frameworks", []):
                        llm_deps.append({"name": fw, "type": "framework"})
                    for db in ai_tech_stack.get("databases", []):
                        llm_deps.append({"name": db, "type": "database"})
                    for out in ai_deps_data.get("outdated", []):
                        if isinstance(out, dict) and "name" in out:
                            llm_deps.append({"name": out["name"], "type": "package"})
                    for vul in ai_deps_data.get("vulnerable", []):
                        if isinstance(vul, dict) and "name" in vul:
                            llm_deps.append({"name": vul["name"], "type": "package"})

                    # Deduplicate
                    unique_deps = {d["name"]: d for d in llm_deps}.values()
                    
                    # Find manifest node, or just use the first node
                    manifest_node = next((n["id"] for n in graph_data["nodes"] if "package.json" in n["id"] or "requirements.txt" in n["id"]), None)
                    
                    for dep in unique_deps:
                        dep_id = f"ext_dep_{dep['name']}"
                        graph_data["nodes"].append({
                            "id": dep_id,
                            "name": dep["name"],
                            "language": dep["type"],
                            "complexity": 5,
                            "val": 15,
                        })
                        if manifest_node:
                            graph_data["links"].append({
                                "source": manifest_node,
                                "target": dep_id
                            })
                        elif len(graph_data["nodes"]) > 1:
                            graph_data["links"].append({
                                "source": graph_data["nodes"][0]["id"],
                                "target": dep_id
                            })

                except Exception as e:
                    print(f"AI analysis failed, continuing with basic analysis: {e}")
                    # Continue with basic analysis, AI is optional

            dependency_manifests = self._collect_dependency_manifests(repo_path)
            dependency_count = sum(len(manifest["dependencies"]) for manifest in dependency_manifests)

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

    def _calculate_hotspots(self, files: List[Dict]) -> List[Dict]:
        # Sort files by complexity and return top 10
        sorted_files = sorted(files, key=lambda x: x["complexity"], reverse=True)
        return sorted_files[:10]

    def _collect_vulnerabilities(self, files: List[Dict]) -> List[Dict]:
        findings = []
        for f in files:
            for finding in f.get("vulnerabilities", []):
                findings.append({**finding, "file_path": f["file_path"]})
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        return sorted(findings, key=lambda item: (severity_order.get(item.get("severity"), 9), item.get("file_path", ""), item.get("line", 0)))

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

    def _collect_dependency_manifests(self, repo_path: str) -> List[Dict]:
        manifests = []
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            relative_root = os.path.relpath(root, repo_path)

            if "package.json" in files:
                package_path = os.path.join(root, "package.json")
                try:
                    with open(package_path, "r", errors="ignore") as f:
                        data = json.load(f)
                    dependencies = []
                    for section in ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"]:
                        for name, version in data.get(section, {}).items():
                            dependencies.append({"name": name, "version": version, "scope": section})
                    manifests.append({
                        "file_path": os.path.normpath(os.path.join(relative_root, "package.json")).lstrip("./"),
                        "type": "npm",
                        "dependencies": dependencies,
                    })
                except Exception as e:
                    print(f"Error reading package manifest {package_path}: {e}")

            if "requirements.txt" in files:
                req_path = os.path.join(root, "requirements.txt")
                try:
                    dependencies = []
                    with open(req_path, "r", errors="ignore") as f:
                        for raw_line in f:
                            line = raw_line.strip()
                            if not line or line.startswith("#") or line.startswith("-"):
                                continue
                            name = line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].strip()
                            dependencies.append({"name": name, "version": line, "scope": "runtime"})
                    manifests.append({
                        "file_path": os.path.normpath(os.path.join(relative_root, "requirements.txt")).lstrip("./"),
                        "type": "python",
                        "dependencies": dependencies,
                    })
                except Exception as e:
                    print(f"Error reading requirements manifest {req_path}: {e}")
        return manifests

"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import dynamic from "next/dynamic";
import * as THREE from "three";

// ForceGraph3D is not SSR friendly
const ForceGraph3D = dynamic(() => import("react-force-graph-3d"), { ssr: false });

export default function GraphView({ data, onNodeClick }: { data: any; onNodeClick?: (node: any) => void }) {
  const fgRef = useRef<any>();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Extract unique languages from the data for dynamic legend
  const uniqueLanguages = useMemo(() => {
    if (!data || !data.nodes) return [];
    const languages = new Set<string>();
    data.nodes.forEach((node: any) => {
      if (!node.isCentral) {
        languages.add(String(node.language || ""));
      }
    });
    return Array.from(languages).filter(Boolean).sort();
  }, [data]);

  // Enhance graph data with central "User sees this" node and connections
  const enhancedGraphData = useMemo(() => {
    if (!data) return { nodes: [], links: [] };

    // Create central node
    const centralNode = {
      id: "central-user-view",
      name: "Repository Overview",
      path: "Entry point",
      language: "central",
      complexity: 1,
      vulnerabilities: 0,
      val: 28,
      boxWidth: 42,
      boxHeight: 18,
      boxDepth: 8,
      isSummary: true,
      isCentral: true
    };

    // Create links FROM file nodes TO central node (arrows point toward central)
    const centralLinks = data.nodes.map((node: any) => ({
      source: node.id,
      target: "central-user-view",
      // Links point toward the central "User Sees This" node
    }));

    // Combine original data with central node and links
    return {
      nodes: [centralNode, ...data.nodes],
      links: [...centralLinks, ...data.links]
    };
  }, [data]);

  // Center the graph initially after it mounts and data is available
  useEffect(() => {
    if (mounted && fgRef.current && enhancedGraphData && enhancedGraphData.nodes.length > 0) {
      // Position camera to look at the center of the graph (where central node is)
      fgRef.current.cameraPosition(
        { x: 0, y: 0, z: 140 }, // pull back to show more of the graph by default
        { x: 0, y: 0, z: 0 },  // look at origin (where central node will be)
        1500  // smooth transition duration
      );

      fgRef.current.d3Force?.("charge")?.strength(-1200);
      fgRef.current.d3Force?.("collision")?.radius((node: any) => {
        if (node.isCentral) return 24;
        return Math.max(10, Math.min(20, 8 + String(node.name || "").length * 0.3));
      });
      fgRef.current.d3Force?.("link")?.distance((link: any) => {
        const sourceIsCentral = link.source?.isCentral || link.target?.isCentral;
        return sourceIsCentral ? 140 : 95;
      });
    }
  }, [mounted, enhancedGraphData]);

  if (!mounted) return <div className="h-full w-full bg-black/50 animate-pulse flex items-center justify-center">Centering...</div>;

  return (
    <div className="h-full w-full relative flex items-center justify-center">
      <ForceGraph3D
        ref={fgRef}
        graphData={enhancedGraphData}
        backgroundColor="#0a0a0a"
        nodeLabel={(node: any) => {
          if (node.isCentral) {
            return "Repository Overview";
          }
          const vulnerabilityText = node.vulnerabilities > 0 ? `\nSecurity findings: ${node.vulnerabilities}` : "";
          return `${node.name}\n${node.path || ""}${vulnerabilityText}`;
        }}
        nodeVal={(node: any) => node.val}
        nodeThreeObject={(node: any) => createNodeCard(node)}
        nodeThreeObjectExtend={true}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={0.5}
        linkCurvature={0.15}
        linkColor={(link: any) => {
          const source = link.source;
          const target = link.target;
          const sourceIsCentral = source?.isCentral || source?.id === "central-user-view";
          const targetIsCentral = target?.isCentral || target?.id === "central-user-view";

          if (sourceIsCentral || targetIsCentral) {
            return "rgba(0, 255, 65, 0.55)";
          }

          const sourceFinding = Number(source?.vulnerabilities || 0);
          const targetFinding = Number(target?.vulnerabilities || 0);
          if (sourceFinding > 0 || targetFinding > 0) {
            return "rgba(239, 68, 68, 0.7)";
          }

          return "rgba(0, 255, 65, 0.2)";
        }}
        linkWidth={({ source, target }: any) => {
          // Make links to/from central node slightly wider
          const sourceIsCentral = source.id === "central-user-view" || source.isCentral;
          const targetIsCentral = target.id === "central-user-view" || target.isCentral;

          if (sourceIsCentral || targetIsCentral) {
            // Wider links for central connections
            return Math.sqrt(source.val * target.val) * 0.15;
          }
          return Math.sqrt(source.val * target.val) * 0.1;
        }}
        onNodeClick={(node: any) => {
          // Don't allow clicking on central node to avoid confusion
          if (node.isCentral) return;

          // Aim at node from outside
          const distance = 40;
          const distRatio = 1 + distance / Math.hypot(node.x, node.y, node.z);

          fgRef.current.cameraPosition(
            { x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio }, // new pos
            node, // lookAt ({ x, y, z })
            3000  // ms transition duration
          );

          if (onNodeClick) {
            onNodeClick(node);
          }
        }}
      />
      {/* Dynamic Language Legend */}
      <div className="absolute bottom-4 left-4 text-[10px] uppercase tracking-widest text-[#444] bg-black/50 p-2 border border-[#222]">
        <div className="flex flex-col items-start gap-1">
          <div className="text-[9px] text-[#00ff41] font-bold">Nodes:</div>
          <div className="flex flex-wrap gap-2">
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-sm bg-[#00ff41]" />
              <span className="text-[9px]">Files</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-sm bg-red-500" />
              <span className="text-[9px]">Findings</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function createNodeCard(node: any) {
  const width = node.isCentral ? 28 : Math.max(12, Math.min(18, 10 + String(node.name || "").length * 0.16));
  const height = node.isCentral ? 12 : Math.max(8, Math.min(12, 8 + Math.max(0, String(node.path || "").split("/").length - 1) * 0.4));
  const depth = node.isCentral ? 3 : 2.5;

  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 512;
  const context = canvas.getContext("2d");
  if (!context) return new THREE.Group();

  const isFinding = Number(node.vulnerabilities || 0) > 0;
  const border = isFinding ? "rgba(239, 68, 68, 0.95)" : node.isCentral ? "rgba(0, 255, 65, 0.9)" : "rgba(75, 146, 255, 0.8)";

  roundRect(context, 22, 24, canvas.width - 44, canvas.height - 48, 42);
  context.fillStyle = "rgba(0, 0, 0, 0)";
  context.fill();
  context.lineWidth = 10;
  context.strokeStyle = border;
  context.stroke();

  context.fillStyle = isFinding ? "#fecaca" : "#e5e7eb";
  context.font = "bold 42px Inter, sans-serif";
  context.textBaseline = "top";
  wrapText(context, String(node.name || "Untitled"), 64, 72, canvas.width - 128, 50, 2);

  context.fillStyle = isFinding ? "#fca5a5" : "#9ca3af";
  context.font = "28px Inter, sans-serif";
  const pathText = String(node.path || node.id || "");
  wrapText(context, pathText, 64, 180, canvas.width - 128, 34, 2);

  if (isFinding) {
    context.fillStyle = "#fecaca";
    context.font = "bold 28px Inter, sans-serif";
    context.fillText(`Findings: ${Number(node.vulnerabilities || 0)}`, 64, 316);
  } else {
    context.fillStyle = "#86efac";
    context.font = "bold 24px Inter, sans-serif";
    context.fillText(String(node.language || "file").toUpperCase(), 64, 316);
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;

  const material = new THREE.MeshBasicMaterial({
    map: texture,
    transparent: true,
    opacity: 0,
    depthWrite: false,
  });
  const geometry = new THREE.BoxGeometry(width, height, depth);
  const mesh = new THREE.Mesh(geometry, material);

  const borderMaterial = new THREE.LineBasicMaterial({ color: border, transparent: true, opacity: 0.95 });
  const borderMesh = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(width + 0.8, height + 0.8, depth + 0.8)), borderMaterial);

  const group = new THREE.Group();
  group.add(mesh);
  group.add(borderMesh);
  return group;
}

function roundRect(context: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number) {
  context.beginPath();
  context.moveTo(x + radius, y);
  context.lineTo(x + width - radius, y);
  context.quadraticCurveTo(x + width, y, x + width, y + radius);
  context.lineTo(x + width, y + height - radius);
  context.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  context.lineTo(x + radius, y + height);
  context.quadraticCurveTo(x, y + height, x, y + height - radius);
  context.lineTo(x, y + radius);
  context.quadraticCurveTo(x, y, x + radius, y);
  context.closePath();
}

function wrapText(
  context: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  lineHeight: number,
  maxLines: number,
) {
  const words = text.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let current = "";

  words.forEach((word) => {
    const trial = current ? `${current} ${word}` : word;
    if (context.measureText(trial).width <= maxWidth || !current) {
      current = trial;
    } else {
      lines.push(current);
      current = word;
    }
  });

  if (current) lines.push(current);
  const displayLines = lines.slice(0, maxLines);

  displayLines.forEach((line, index) => {
    context.fillText(line, x, y + index * lineHeight);
  });

  if (lines.length > maxLines) {
    context.fillText("...", x, y + (maxLines - 1) * lineHeight);
  }
}

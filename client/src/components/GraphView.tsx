"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import dynamic from "next/dynamic";

// ForceGraph3D is not SSR friendly
const ForceGraph3D = dynamic(() => import("react-force-graph-3d"), { ssr: false });

export default function GraphView({ data }: { data: any }) {
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
      name: "User Sees This",
      language: "central",
      complexity: 1,
      vulnerabilities: 0,
      val: 15, // Make it larger than other nodes
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
        { x: 0, y: 0, z: 60 }, // camera position - slightly further back to see central node
        { x: 0, y: 0, z: 0 },  // look at origin (where central node will be)
        1500  // smooth transition duration
      );
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
            return "User\nSees\nThis";
          }
          return `${node.name} (${node.language}) - complexity ${node.complexity || 1}, findings ${node.vulnerabilities || 0}`;
        }}
        nodeColor={(node: any) => {
          if (node.isCentral) {
            // Special color for central node - pulsating/glowing effect
            return "#00ff41";
          }
          if (node.vulnerabilities > 0) return "#ef4444";
          switch (node.language) {
            case "python": return "#3776ab";
            case "javascript": return "#f7df1e";
            case "typescript": return "#3178c6";
            case "framework": return "#a855f7"; // purple
            case "database": return "#eab308";  // yellow
            case "package": return "#3b82f6";   // blue
            default: return "#00ff41";
          }
        }}
        nodeVal={(node: any) => node.val}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={0.5}
        linkCurvature={0.3}
        linkColor={() => {
          // Central links could be a different style, but for now keep consistent
          return "#00ff41";
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
        }}
      />
      {/* Dynamic Language Legend */}
      <div className="absolute bottom-4 left-4 text-[10px] uppercase tracking-widest text-[#444] bg-black/50 p-2 border border-[#222]">
        <div className="flex flex-col items-start gap-1">
          <div className="text-[9px] text-[#00ff41] font-bold">Languages:</div>
          <div className="flex flex-wrap gap-2">
            {uniqueLanguages.map((lang) => {
              const colorMap: Record<string, string> = {
                python: "#3776ab",
                javascript: "#f7df1e",
                typescript: "#3178c6",
                framework: "#a855f7",
                database: "#eab308",
                package: "#3b82f6",
              };
              const color = colorMap[lang.toLowerCase()] || "#00ff41";
              return (
                <div key={lang} className="flex items-center gap-1">
                  <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                  <span className="text-[9px]">{lang}</span>
                </div>
              );
            })}
            {/* Always show findings indicator */}
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-full bg-red-500" />
              <span className="text-[9px]">Findings</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

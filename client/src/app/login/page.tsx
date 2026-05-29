"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import AnimatedShaderBackground from "@/components/ui/animated-shader-background";
import { Loader2, BookOpen } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const { user, loading, loginWithGoogle } = useAuth();

  useEffect(() => {
    if (!loading && user) {
      router.push("/dashboard");
    }
  }, [user, loading, router]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black">
        <Loader2 className="animate-spin text-[#00ff41]" size={32} />
      </div>
    );
  }

  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-black">
      <AnimatedShaderBackground />

      <div className="absolute inset-0 flex items-center justify-center z-10">
        <div className="text-center space-y-8 px-4">
          <div className="space-y-4">
            <h1 className="text-5xl md:text-6xl font-bold text-white tracking-tighter">
              CodeLens
            </h1>
            <p className="text-xl text-[#888] max-w-md mx-auto">
              AI-Powered Codebase Analysis & Visualization
            </p>
          </div>

          <div className="flex flex-col items-center gap-3">
            <button
              onClick={loginWithGoogle}
              className="px-8 py-3 bg-[#00ff41] text-black rounded-lg font-bold text-lg hover:bg-[#00ff41]/90 transition-all shadow-lg hover:shadow-xl"
            >
              Login with Google
            </button>

            <button
              onClick={() => router.push("/documentation")}
              className="px-6 py-2.5 bg-transparent text-[#00ff41] border border-[#00ff41]/70 rounded-md font-semibold text-sm hover:bg-[#00ff41]/10 hover:border-[#00ff41] transition-all inline-flex items-center gap-2"
            >
              <BookOpen size={16} /> Documentation
            </button>
          </div>

          <p className="text-[#666] text-sm">
            Analyze any public GitHub repository with AI-powered insights
          </p>
        </div>
      </div>
    </div>
  );
}

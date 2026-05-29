(globalThis.TURBOPACK||(globalThis.TURBOPACK=[])).push(["object"==typeof document?document.currentScript:void 0,94542,e=>{"use strict";var i=e.i(18050),t=e.i(71645),n=e.i(18566),s=e.i(54338),o=e.i(32009);let r=()=>{let e=(0,t.useRef)(null);return(0,t.useEffect)(()=>{let i,t=e.current,n=new o.Scene,s=new o.OrthographicCamera(-1,1,1,-1,0,1),r=new o.WebGLRenderer({antialias:!0});r.setSize(window.innerWidth,window.innerHeight),t.appendChild(r.domElement);let a=new o.ShaderMaterial({uniforms:{iTime:{value:0},iResolution:{value:new o.Vector2(window.innerWidth,window.innerHeight)}},vertexShader:`
        void main() {
          gl_Position = vec4(position, 1.0);
        }
      `,fragmentShader:`
        uniform float iTime;
        uniform vec2 iResolution;

        #define NUM_OCTAVES 3

        float rand(vec2 n) {
          return fract(sin(dot(n, vec2(12.9898, 4.1414))) * 43758.5453);
        }

        float noise(vec2 p) {
          vec2 ip = floor(p);
          vec2 u = fract(p);
          u = u*u*(3.0-2.0*u);

          float res = mix(
            mix(rand(ip), rand(ip + vec2(1.0, 0.0)), u.x),
            mix(rand(ip + vec2(0.0, 1.0)), rand(ip + vec2(1.0, 1.0)), u.x), u.y);
          return res * res;
        }

        float fbm(vec2 x) {
          float v = 0.0;
          float a = 0.3;
          vec2 shift = vec2(100);
          mat2 rot = mat2(cos(0.5), sin(0.5), -sin(0.5), cos(0.5));
          for (int i = 0; i < NUM_OCTAVES; ++i) {
            v += a * noise(x);
            x = rot * x * 2.0 + shift;
            a *= 0.4;
          }
          return v;
        }

        void main() {
          vec2 shake = vec2(sin(iTime * 1.2) * 0.005, cos(iTime * 2.1) * 0.005);
          vec2 p = ((gl_FragCoord.xy + shake * iResolution.xy) - iResolution.xy * 0.5) / iResolution.y * mat2(6.0, -4.0, 4.0, 6.0);
          vec2 v;
          vec4 o = vec4(0.0);

          float f = 2.0 + fbm(p + vec2(iTime * 5.0, 0.0)) * 0.5;

          for (float i = 0.0; i < 35.0; i++) {
            v = p + cos(i * i + (iTime + p.x * 0.08) * 0.025 + i * vec2(13.0, 11.0)) * 3.5 + vec2(sin(iTime * 3.0 + i) * 0.003, cos(iTime * 3.5 - i) * 0.003);
            float tailNoise = fbm(v + vec2(iTime * 0.5, i)) * 0.3 * (1.0 - (i / 35.0));
            vec4 auroraColors = vec4(
              0.1 + 0.3 * sin(i * 0.2 + iTime * 0.4),
              0.3 + 0.5 * cos(i * 0.3 + iTime * 0.5),
              0.7 + 0.3 * sin(i * 0.4 + iTime * 0.3),
              1.0
            );
            vec4 currentContribution = auroraColors * exp(sin(i * i + iTime * 0.8)) / length(max(v, vec2(v.x * f * 0.015, v.y * 1.5)));
            float thinnessFactor = smoothstep(0.0, 1.0, i / 35.0) * 0.6;
            o += currentContribution * (1.0 + tailNoise * 0.8) * thinnessFactor;
          }

          o = tanh(pow(o / 100.0, vec4(1.6)));
          gl_FragColor = o * 1.5;
        }
      `}),l=new o.PlaneGeometry(2,2),c=new o.Mesh(l,a);n.add(c);let d=()=>{a.uniforms.iTime.value+=.016,r.render(n,s),i=requestAnimationFrame(d)};d();let m=()=>{r.setSize(window.innerWidth,window.innerHeight),a.uniforms.iResolution.value.set(window.innerWidth,window.innerHeight)};return window.addEventListener("resize",m),()=>{cancelAnimationFrame(i),window.removeEventListener("resize",m),t.removeChild(r.domElement),l.dispose(),a.dispose(),r.dispose()}},[]),(0,i.jsx)("div",{ref:e,className:"relative overflow-x-hidden",children:(0,i.jsx)("div",{className:"relative z-10 divider"})})};var a=e.i(31278);e.s(["default",0,function(){let e=(0,n.useRouter)(),{user:o,loading:l,loginWithGoogle:c}=(0,s.useAuth)();return((0,t.useEffect)(()=>{!l&&o&&e.push("/dashboard")},[o,l,e]),l)?(0,i.jsx)("div",{className:"min-h-screen flex items-center justify-center bg-black",children:(0,i.jsx)(a.Loader2,{className:"animate-spin text-[#00ff41]",size:32})}):(0,i.jsxs)("div",{className:"relative min-h-screen w-full overflow-hidden bg-black",children:[(0,i.jsx)(r,{}),(0,i.jsx)("div",{className:"absolute inset-0 flex items-center justify-center z-10",children:(0,i.jsxs)("div",{className:"text-center space-y-8 px-4",children:[(0,i.jsxs)("div",{className:"space-y-4",children:[(0,i.jsx)("h1",{className:"text-5xl md:text-6xl font-bold text-white tracking-tighter",children:"CodeLens"}),(0,i.jsx)("p",{className:"text-xl text-[#888] max-w-md mx-auto",children:"AI-Powered Codebase Analysis & Visualization"})]}),(0,i.jsx)("button",{onClick:c,className:"px-8 py-3 bg-[#00ff41] text-black rounded-lg font-bold text-lg hover:bg-[#00ff41]/90 transition-all shadow-lg hover:shadow-xl",children:"Login with Google"}),(0,i.jsx)("p",{className:"text-[#666] text-sm",children:"Analyze any public GitHub repository with AI-powered insights"})]})})]})}],94542)}]);
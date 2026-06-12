import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "hsl(0 0% 100%)",
        foreground: "hsl(222 47% 11%)",
        muted: "hsl(210 40% 96%)",
        "muted-foreground": "hsl(215 16% 47%)",
        border: "hsl(214 32% 91%)",
        primary: "hsl(222 47% 11%)",
        "primary-foreground": "hsl(0 0% 100%)",
        accent: "hsl(221 83% 53%)",
        "accent-foreground": "hsl(0 0% 100%)",
        destructive: "hsl(0 84% 60%)",
      },
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "Pretendard", "system-ui",
               "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;

import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Vendored AgentPrism components (degit from evilmartians/agent-prism):
    // third-party code kept as close to upstream as possible, not held to
    // this repo's lint rules.
    "src/components/agent-prism/**",
  ]),
]);

export default eslintConfig;

/**
 * ASTRA — Jest Configuration
 * ===========================
 * File: frontend/jest.config.ts
 *
 * Jest dev deps are not installed in the standard image. tsconfig.json
 * excludes this file from the project typecheck so the missing
 * `import type { Config } from "jest"` reference doesn't break
 * `npx tsc --noEmit` or `next build`. Install `jest`, `ts-jest`,
 * `@types/jest`, `@testing-library/react`, `@testing-library/jest-dom`
 * to enable jest test runs locally.
 */

import type { Config } from "jest";

const config: Config = {
  preset: "ts-jest",
  testEnvironment: "jsdom",
  roots: ["<rootDir>/__tests__"],
  setupFilesAfterSetup: ["<rootDir>/__tests__/setup.ts"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
  },
  transform: {
    "^.+\\.tsx?$": [
      "ts-jest",
      { tsconfig: "tsconfig.json" },
    ],
  },
  collectCoverageFrom: [
    "src/**/*.{ts,tsx}",
    "!src/**/*.d.ts",
  ],
};

export default config;

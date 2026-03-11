/**
 * ASTRA — Jest Configuration
 * ===========================
 * File: frontend/jest.config.ts
 *
 * NOTE: You need to install dev deps first:
 *   npm i -D jest ts-jest @types/jest @testing-library/react @testing-library/jest-dom
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

/**
 * ASTRA — AI Components Barrel Export
 * ======================================
 * File: frontend/src/components/ai/index.ts
 * Path: C:\Users\Mason\Documents\ASTRA\frontend\src\components\ai\index.ts
 */

// Quality analysis (existed before Prompts 1-3)
export { default as QualityPanel } from './QualityPanel';

// Semantic analysis — Prompt 1 (duplicates, trace suggestions, verification)
export { default as DuplicateChecker } from './DuplicateChecker';
export { default as TraceSuggestionsPanel } from './TraceSuggestionsPanel';
export { default as VerificationSuggestionPanel } from './VerificationSuggestionPanel';

// AI Writing Assistant — Prompt 3
export { default as AIWritingAssistant, AIWriterLauncher } from './AIWritingAssistant';

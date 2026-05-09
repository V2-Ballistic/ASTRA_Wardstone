// ══════════════════════════════════════════════════════════════
//  ASTRA — System Architecture API client
//  TDD-SYSARCH-002 Phase 3
// ══════════════════════════════════════════════════════════════

import api from './api';
import type { SystemArchGraphResponse } from './sysarch-types';

export const sysarchAPI = {
  /**
   * GET /api/v1/system-architecture/graph?project_id=N
   * Single round-trip payload of {systems, units, edges}.
   */
  getGraph: (projectId: number) =>
    api.get<SystemArchGraphResponse>(
      `/system-architecture/graph?project_id=${projectId}`,
    ),
};

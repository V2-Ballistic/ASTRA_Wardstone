// CADPORT-REBUILD-003: API client for the Assemblies tab.
// Mirrors the parts-api.ts axios pattern (auth + base URL handled by
// the shared `api` instance).

import api from './api';

export interface CadportComponent {
  catalog_part_id: number | null;
  cadport_part_id: string;
  instance_name: string;
  quantity: number;
  suppressed: boolean;
  wpn: string | null;
  display_name: string | null;
  mass_kg: number | null;
  material: string | null;
  transform: number[][] | null; // 4x4
  part_yaml_document_id: number | null;
  project_part_exists: boolean;
  project_part_id: number | null;
}

export interface CadportAssembly {
  id: number;
  assembly_id: string;
  project_id: number;
  project_code: string | null;
  project_name: string | null;
  display_name: string;
  source_file: string;
  content_hash: string | null;
  total_mass_kg: number;
  center_of_mass: number[];
  solidworks_version: string | null;
  component_count: number;
  assembly_yaml_document_id: number | null;
  assembly_yaml_filename: string | null;
  components: CadportComponent[];
}

export const cadportAPI = {
  listAssemblies: (projectId: number) =>
    api.get<CadportAssembly[]>('/cadport-assemblies', {
      params: { project_id: projectId },
    }),

  getAssembly: (pk: number) =>
    api.get<CadportAssembly>(`/cadport-assemblies/${pk}`),

  // L8 — "Add to project" creates a project_part from a catalog_part
  // (AD-3: reuse the existing endpoint, no new path).
  addPartToProject: (projectId: number, catalogPartId: number, designation?: string) =>
    api.post(`/projects/${projectId}/parts/`, {
      catalog_part_id: catalogPartId,
      quantity: 1,
      quantity_unit: 'each',
      designation: designation ?? undefined,
    }),

  // AD-4 — YAML download via the existing supplier_documents file route.
  documentFileUrl: (docId: number) =>
    `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'}/catalog/documents/${docId}/file`,
};

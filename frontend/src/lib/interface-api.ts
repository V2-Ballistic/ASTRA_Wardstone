// ══════════════════════════════════════════════════════════════
//  ASTRA — Interface Module API Client
//  Typed Axios calls for all interface endpoints
//
//  File: frontend/src/lib/interface-api.ts
//  Path: C:\Users\Mason\Documents\ASTRA\frontend\src\lib\interface-api.ts
// ══════════════════════════════════════════════════════════════

import api from './api';
import type {
  System, SystemDetail,
  UnitSummary, Unit, UnitDetail,
  Connector, ConnectorWithPins, PinoutData,
  Pin, PinBusAssignment,
  BusDefinition, BusWithMessages, BusUtilization,
  MessageSummary, MessageDefinition, MessageWithFields, ByteMapLayout,
  MessageField,
  WireHarness, WireHarnessDetail,
  Wire,
  Interface,
  UnitEnvironmentalSpec,
  InterfaceRequirementLink,
  AutoReqLog,
  N2MatrixResponse, BlockDiagramResponse, SignalTraceResult,
  InterfaceCoverageResponse, ImpactPreview,
  ImportPreviewResponse, ImportConfirmResponse,
} from './interface-types';

const BASE = '/interfaces';
const IO = '/interfaces/io';

export const interfaceAPI = {

  // ══════════════════════════════════════
  //  Systems
  // ══════════════════════════════════════

  listSystems: (projectId: number, mode: 'flat' | 'tree' = 'flat') =>
    api.get<System[]>(`${BASE}/systems`, { params: { project_id: projectId, mode } }),

  createSystem: (projectId: number, data: Partial<System>) =>
    api.post<System>(`${BASE}/systems?project_id=${projectId}`, data),

  getSystem: (id: number) =>
    api.get<SystemDetail>(`${BASE}/systems/${id}`),

  updateSystem: (id: number, data: Partial<System>) =>
    api.patch<System>(`${BASE}/systems/${id}`, data),

  deleteSystem: (id: number, force = false) =>
    api.delete(`${BASE}/systems/${id}`, { params: { force } }),

  // ══════════════════════════════════════
  //  Units
  // ══════════════════════════════════════

  listUnits: (projectId: number, params?: {
    system_id?: number; unit_type?: string; search?: string;
    skip?: number; limit?: number;
  }) =>
    api.get<UnitSummary[]>(`${BASE}/units`, { params: { project_id: projectId, ...params } }),

  createUnit: (projectId: number, data: Partial<Unit>) =>
    api.post<Unit>(`${BASE}/units?project_id=${projectId}`, data),

  getUnit: (id: number) =>
    api.get<UnitDetail>(`${BASE}/units/${id}`),

  updateUnit: (id: number, data: Partial<Unit>) =>
    api.patch<Unit>(`${BASE}/units/${id}`, data),

  deleteUnit: (id: number, confirm = false) =>
    api.delete(`${BASE}/units/${id}`, { params: { confirm } }),

  getUnitSpecs: (id: number) =>
    api.get(`${BASE}/units/${id}/specifications`),

  // ══════════════════════════════════════
  //  Connectors
  // ══════════════════════════════════════

  listConnectors: (unitId: number) =>
    api.get<Connector[]>(`${BASE}/connectors`, { params: { unit_id: unitId } }),

  createConnector: (data: Partial<Connector> & { pins?: Partial<Pin>[] }) =>
    api.post<ConnectorWithPins | Connector>(`${BASE}/connectors`, data),

  getConnector: (id: number) =>
    api.get<ConnectorWithPins>(`${BASE}/connectors/${id}`),

  getPinout: (id: number) =>
    api.get<PinoutData>(`${BASE}/connectors/${id}/pinout`),

  updateConnector: (id: number, data: Partial<Connector>) =>
    api.patch<Connector>(`${BASE}/connectors/${id}`, data),

  deleteConnector: (id: number, force = false) =>
    api.delete(`${BASE}/connectors/${id}`, { params: { force } }),

  // ══════════════════════════════════════
  //  Pins
  // ══════════════════════════════════════

  batchAddPins: (connectorId: number, pins: Partial<Pin>[]) =>
    api.post<Pin[]>(`${BASE}/connectors/${connectorId}/pins`, { pins }),

  autoGeneratePins: (connectorId: number) =>
    api.post<Pin[]>(`${BASE}/connectors/${connectorId}/pins/auto-generate`),

  updatePin: (id: number, data: Partial<Pin>) =>
    api.patch<Pin>(`${BASE}/pins/${id}`, data),

  deletePin: (id: number) =>
    api.delete(`${BASE}/pins/${id}`),

  searchPins: (projectId: number, signalName: string) =>
    api.get(`${BASE}/pins/search`, { params: { project_id: projectId, signal_name: signalName } }),

  // ══════════════════════════════════════
  //  Buses
  // ══════════════════════════════════════

  listBuses: (params: { unit_id?: number; project_id?: number; bus_name_network?: string }) =>
    api.get<BusDefinition[]>(`${BASE}/buses`, { params }),

  createBus: (data: Partial<BusDefinition>) =>
    api.post<BusDefinition>(`${BASE}/buses`, data),

  getBus: (id: number) =>
    api.get<BusWithMessages>(`${BASE}/buses/${id}`),

  updateBus: (id: number, data: Partial<BusDefinition>) =>
    api.patch<BusDefinition>(`${BASE}/buses/${id}`, data),

  deleteBus: (id: number, confirm = false) =>
    api.delete(`${BASE}/buses/${id}`, { params: { confirm } }),

  assignPins: (busId: number, assignments: { pin_id: number; pin_role: string; notes?: string }[]) =>
    api.post<PinBusAssignment[]>(`${BASE}/buses/${busId}/pin-assignments`, assignments),

  removePinAssignment: (id: number) =>
    api.delete(`${BASE}/buses/pin-assignments/${id}`),

  getBusUtilization: (id: number) =>
    api.get<BusUtilization>(`${BASE}/buses/${id}/utilization`),

  // ══════════════════════════════════════
  //  Messages
  // ══════════════════════════════════════

  listMessages: (params: { bus_id?: number; unit_id?: number; project_id?: number; label?: string }) =>
    api.get<MessageSummary[]>(`${BASE}/messages`, { params }),

  createMessage: (data: Partial<MessageDefinition> & { fields?: Partial<MessageField>[] }) =>
    api.post<MessageWithFields | MessageDefinition>(`${BASE}/messages`, data),

  getMessage: (id: number) =>
    api.get<MessageWithFields>(`${BASE}/messages/${id}`),

  updateMessage: (id: number, data: Partial<MessageDefinition>) =>
    api.patch<MessageDefinition>(`${BASE}/messages/${id}`, data),

  deleteMessage: (id: number, confirm = false) =>
    api.delete(`${BASE}/messages/${id}`, { params: { confirm } }),

  getByteMap: (id: number) =>
    api.get<ByteMapLayout>(`${BASE}/messages/${id}/byte-map`),

  // ══════════════════════════════════════
  //  Message Fields
  // ══════════════════════════════════════

  batchAddFields: (messageId: number, fields: Partial<MessageField>[]) =>
    api.post<MessageField[]>(`${BASE}/messages/${messageId}/fields`, { fields }),

  updateField: (id: number, data: Partial<MessageField>) =>
    api.patch<MessageField>(`${BASE}/fields/${id}`, data),

  deleteField: (id: number) =>
    api.delete(`${BASE}/fields/${id}`),

  // ══════════════════════════════════════
  //  Harnesses
  // ══════════════════════════════════════

  listHarnesses: (projectId: number, params?: { from_unit_id?: number; to_unit_id?: number }) =>
    api.get<WireHarness[]>(`${BASE}/harnesses`, { params: { project_id: projectId, ...params } }),

  createHarness: (data: Partial<WireHarness>) =>
    api.post<WireHarness>(`${BASE}/harnesses`, data),

  getHarness: (id: number) =>
    api.get<WireHarnessDetail>(`${BASE}/harnesses/${id}`),

  updateHarness: (id: number, data: Partial<WireHarness>) =>
    api.patch<WireHarness>(`${BASE}/harnesses/${id}`, data),

  deleteHarness: (id: number, confirm = false) =>
    api.delete(`${BASE}/harnesses/${id}`, { params: { confirm } }),

  // ══════════════════════════════════════
  //  Wires
  // ══════════════════════════════════════

  batchAddWires: (harnessId: number, wires: Partial<Wire>[]) =>
    api.post(`${BASE}/harnesses/${harnessId}/wires`, { wires }),

  autoWire: (harnessId: number) =>
    api.post(`${BASE}/harnesses/${harnessId}/auto-wire`),

  updateWire: (id: number, data: Partial<Wire>) =>
    api.patch<Wire>(`${BASE}/wires/${id}`, data),

  deleteWire: (id: number, confirm = false) =>
    api.delete(`${BASE}/wires/${id}`, { params: { confirm } }),

  searchWires: (projectId: number, signalName: string) =>
    api.get<Wire[]>(`${BASE}/wires/search`, { params: { project_id: projectId, signal_name: signalName } }),

  // ══════════════════════════════════════
  //  Signal Trace + Visualization
  // ══════════════════════════════════════

  traceSignal: (projectId: number, signalName: string) =>
    api.get<SignalTraceResult>(`${BASE}/signal-trace`, { params: { project_id: projectId, signal_name: signalName } }),

  getN2Matrix: (projectId: number, level: 'system' | 'unit' = 'system') =>
    api.get<N2MatrixResponse>(`${BASE}/n2-matrix`, { params: { project_id: projectId, level } }),

  getBlockDiagram: (projectId: number) =>
    api.get<BlockDiagramResponse>(`${BASE}/block-diagram`, { params: { project_id: projectId } }),

  // ══════════════════════════════════════
  //  Requirement Links + Coverage
  // ══════════════════════════════════════

  createReqLink: (data: Partial<InterfaceRequirementLink>) =>
    api.post<InterfaceRequirementLink>(`${BASE}/req-links`, data),

  listReqLinks: (params: { entity_type?: string; entity_id?: number; requirement_id?: number }) =>
    api.get<InterfaceRequirementLink[]>(`${BASE}/req-links`, { params }),

  deleteReqLink: (id: number) =>
    api.delete(`${BASE}/req-links/${id}`),

  getCoverage: (projectId: number) =>
    api.get<InterfaceCoverageResponse>(`${BASE}/coverage`, { params: { project_id: projectId } }),

  // ══════════════════════════════════════
  //  Impact Analysis
  // ══════════════════════════════════════

  previewImpact: (data: {
    action: 'delete_wire' | 'delete_bus' | 'edit_bus' | 'edit_message' | 'delete_unit';
    entity_id: number | number[];
    changes?: Record<string, any>;
  }) =>
    api.post<ImpactPreview>(`${BASE}/impact/preview`, data),

  executeImpact: (data: {
    affected_req_ids: number[];
    action: 'delete_requirements' | 'orphan_requirements' | 'mark_for_review';
    change_description?: string;
    project_id?: number;
  }) =>
    api.post(`${BASE}/impact/execute`, data),

  // ══════════════════════════════════════
  //  Import / Export
  // ══════════════════════════════════════

  downloadTemplate: () =>
    api.post(`${IO}/import/template`, null, { responseType: 'blob' }),

  importPreview: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post<ImportPreviewResponse>(`${IO}/import/preview`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  importConfirm: (projectId: number, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post<ImportConfirmResponse>(`${IO}/import/confirm?project_id=${projectId}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  exportUnits: (projectId: number) =>
    api.get(`${IO}/export/units`, { params: { project_id: projectId }, responseType: 'blob' }),

  exportHarness: (harnessId: number) =>
    api.get(`${IO}/export/harness/${harnessId}`, { responseType: 'blob' }),

  exportAllWiring: (projectId: number) =>
    api.get(`${IO}/export/all-wiring`, { params: { project_id: projectId }, responseType: 'blob' }),

  exportICDData: (projectId: number) =>
    api.get(`${IO}/export/icd-data`, { params: { project_id: projectId }, responseType: 'blob' }),
};

// ══════════════════════════════════════
//  Export download helper
// ══════════════════════════════════════

export function downloadBlob(response: any, fallbackFilename: string) {
  const disposition = response.headers?.['content-disposition'] || '';
  const match = disposition.match(/filename=([^;]+)/);
  const filename = match ? match[1].replace(/"/g, '') : fallbackFilename;

  const url = URL.createObjectURL(new Blob([response.data]));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

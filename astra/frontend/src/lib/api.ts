import axios from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('astra_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Handle 401s globally
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      localStorage.removeItem('astra_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;

// ── Auth ──
export const authAPI = {
  login: (username: string, password: string) =>
    api.post('/auth/login', new URLSearchParams({ username, password }), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    }),
  register: (data: any) => api.post('/auth/register', data),
  me: () => api.get('/auth/me'),
};

// ── Projects ──
export const projectsAPI = {
  list: () => api.get('/projects/'),
  create: (data: any) => api.post('/projects/', data),
  get: (id: number) => api.get(`/projects/${id}`),
};

// ── Requirements ──
export const requirementsAPI = {
  list: (projectId: number, params?: any) =>
    api.get('/requirements/', { params: { project_id: projectId, ...params } }),
  get: (id: number) => api.get(`/requirements/${id}`),
  create: (projectId: number, data: any) =>
    api.post(`/requirements/?project_id=${projectId}`, data),
  update: (id: number, data: any) => api.patch(`/requirements/${id}`, data),
  delete: (id: number) => api.delete(`/requirements/${id}`),
  qualityCheck: (statement: string, title?: string, rationale?: string) =>
    api.post('/requirements/quality-check', null, { params: { statement, title, rationale } }),
};

// ── Source Artifacts ──
export const artifactsAPI = {
  list: (projectId: number) => api.get('/artifacts/', { params: { project_id: projectId } }),
  create: (projectId: number, data: any) =>
    api.post(`/artifacts/?project_id=${projectId}`, data),
};

// ── Traceability ──
export const traceabilityAPI = {
  listLinks: (projectId: number, params?: any) =>
    api.get('/traceability/links', { params: { project_id: projectId, ...params } }),
  createLink: (data: any) => api.post('/traceability/links', data),
  deleteLink: (id: number) => api.delete(`/traceability/links/${id}`),
  getMatrix: (projectId: number) =>
    api.get('/traceability/matrix', { params: { project_id: projectId } }),
  getCoverage: (projectId: number) =>
    api.get('/traceability/coverage', { params: { project_id: projectId } }),
};

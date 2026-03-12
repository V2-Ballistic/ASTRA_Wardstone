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
  restore: (id: number) => api.post(`/requirements/${id}/restore`),
  clone: (id: number) => api.post(`/requirements/${id}/clone`),
  getHistory: (id: number) => api.get(`/requirements/${id}/history`),
  getComments: (id: number) => api.get(`/requirements/${id}/comments`),
  postComment: (id: number, content: string, parentId?: number) =>
    api.post(`/requirements/${id}/comments`, { content, parent_id: parentId || null }),
  getTransitions: (status: string) => api.get(`/requirements/status-transitions/${status}`),
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
  getGraph: (projectId: number) =>
    api.get('/traceability/graph', { params: { project_id: projectId } }),
};

// ── Dashboard ──
export const dashboardAPI = {
  getStats: (projectId: number) =>
    api.get('/dashboard/stats', { params: { project_id: projectId } }),
};

// ── Baselines ──
export const baselinesAPI = {
  list: (projectId: number) =>
    api.get('/baselines/', { params: { project_id: projectId } }),
  get: (id: number) => api.get(`/baselines/${id}`),
  create: (data: { name: string; description?: string; project_id: number }) =>
    api.post('/baselines/', data),
  compare: (a: number, b: number) =>
    api.get(`/baselines/compare/${a}/${b}`),
  delete: (id: number) => api.delete(`/baselines/${id}`),
};

// ── Admin (NEW — RBAC) ──
export const adminAPI = {
  // User management
  createUser: (data: {
    username: string;
    email: string;
    password: string;
    full_name: string;
    role?: string;
    department?: string;
  }) => api.post('/admin/users', data),

  listUsers: () => api.get('/admin/users'),

  updateUser: (id: number, data: {
    role?: string;
    full_name?: string;
    department?: string;
    is_active?: boolean;
  }) => api.patch(`/admin/users/${id}`, data),

  deactivateUser: (id: number) => api.delete(`/admin/users/${id}`),

  // Project members
  addProjectMember: (projectId: number, data: {
    user_id: number;
    role_override?: string;
  }) => api.post(`/admin/projects/${projectId}/members`, data),

  listProjectMembers: (projectId: number) =>
    api.get(`/admin/projects/${projectId}/members`),

  removeProjectMember: (projectId: number, userId: number) =>
    api.delete(`/admin/projects/${projectId}/members/${userId}`),
};

// ── Dev (remove in production) ──
export const devAPI = {
  seed: () => api.post('/dev/seed'),
  seedProject: (projectId: number) => api.post(`/dev/seed-project/${projectId}`),
};

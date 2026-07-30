import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_BASE_URL,
});

export function setAuthToken(token: string | null) {
  if (token) {
    api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  } else {
    delete api.defaults.headers.common['Authorization'];
  }
}

// Multi-org (migration 0017, backend api/dependencies.py): every
// request's active org context is resolved from this header if
// present, validated server-side against the caller's real
// memberships (403 if it names an org they're not in). Omitting it
// entirely falls back to the caller's oldest membership -- which is
// why single-org users never need to call this at all.
export function setActiveOrganizationHeader(organizationId: string | null) {
  if (organizationId) {
    api.defaults.headers.common['X-Organization-Id'] = organizationId;
  } else {
    delete api.defaults.headers.common['X-Organization-Id'];
  }
}

import type { ReactElement } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import Login from './pages/Login';
import Tracks from './pages/Tracks';
import TrackCreate from './pages/TrackCreate';
import TrackEdit from './pages/TrackEdit';
import TrackMatches from './pages/TrackMatches';
import TrackJobDocuments from './pages/TrackJobDocuments';
import TrackApplications from './pages/TrackApplications';
import Profile from './pages/Profile';

function ProtectedRoute({ children }: { children: ReactElement }) {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/tracks" element={<ProtectedRoute><Tracks /></ProtectedRoute>} />
      <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
      <Route path="/tracks/new" element={<ProtectedRoute><TrackCreate /></ProtectedRoute>} />
      <Route path="/tracks/:trackId/edit" element={<ProtectedRoute><TrackEdit /></ProtectedRoute>} />
      <Route path="/tracks/:trackId/matches" element={<ProtectedRoute><TrackMatches /></ProtectedRoute>} />
      <Route
        path="/tracks/:trackId/applications"
        element={<ProtectedRoute><TrackApplications /></ProtectedRoute>}
      />
      <Route
        path="/tracks/:trackId/jobs/:jobId/documents"
        element={<ProtectedRoute><TrackJobDocuments /></ProtectedRoute>}
      />
      <Route path="*" element={<Navigate to="/tracks" replace />} />
    </Routes>
  );
}

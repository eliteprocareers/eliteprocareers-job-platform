import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import Login from './pages/Login';
import Tracks from './pages/Tracks';
import TrackMatches from './pages/TrackMatches';

function ProtectedRoute({ children }: { children: JSX.Element }) {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/tracks" element={<ProtectedRoute><Tracks /></ProtectedRoute>} />
      <Route path="/tracks/:trackId/matches" element={<ProtectedRoute><TrackMatches /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/tracks" replace />} />
    </Routes>
  );
}

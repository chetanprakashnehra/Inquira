
import { BrowserRouter, Navigate, Route, Routes, Link } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Dashboard from "./pages/Dashboard";

function Home() {
  const { user, loading } = useAuth();

  if (loading) return <main className="auth-page">Loading...</main>;

  return (
    <main className="app">
      <nav className="navbar">
        <Link to="/" className="brand">
          <span className="brand-icon">I</span>
          Inquira
        </Link>

        <Link
          className="secondary-button"
          to={user ? "/dashboard" : "/login"}
        >
          {user ? "Dashboard" : "Log in"}
        </Link>
      </nav>

      <section className="hero">
        <span className="eyebrow">YOUR DOCUMENTS. YOUR ANSWERS.</span>
        <h1>
          Turn your documents
          <br />
          into <span>knowledge.</span>
        </h1>
        <p className="description">
          Upload documents, ask questions, and get answers grounded
          in your own information.
        </p>

        <Link
          className="primary-button button-link"
          to={user ? "/dashboard" : "/signup"}
        >
          {user ? "Open workspace" : "Get started"}
        </Link>
      </section>
    </main>
  );
}

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();

  if (loading) return <main className="auth-page">Loading...</main>;

  return user ? children : <Navigate to="/login" replace />;
}

function PublicOnlyRoute({ children }) {
  const { user, loading } = useAuth();

  if (loading) return <main className="auth-page">Loading...</main>;

  return user ? <Navigate to="/dashboard" replace /> : children;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Home />} />

          <Route
            path="/login"
            element={
              <PublicOnlyRoute>
                <Login />
              </PublicOnlyRoute>
            }
          />

          <Route
            path="/signup"
            element={
              <PublicOnlyRoute>
                <Signup />
              </PublicOnlyRoute>
            }
          />

          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

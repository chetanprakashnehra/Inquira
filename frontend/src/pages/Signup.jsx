
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export default function Signup() {
  const { signup } = useAuth();
  const navigate = useNavigate();

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      await signup(email, password, fullName);
      navigate("/login", {
        replace: true,
        state: { message: "Account created. Please log in." },
      });
    } catch (err) {
      setError(err.message || "Signup failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <form className="auth-card" onSubmit={handleSubmit}>
        <Link to="/" className="brand">
          <span className="brand-icon">I</span>
          Inquira
        </Link>

        <h1>Create your account</h1>
        <p className="muted">Start building your knowledge workspace.</p>

        <label htmlFor="fullName">Full name (optional)</label>
        <input
          id="fullName"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          placeholder="Your name"
          autoComplete="name"
        />

        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          autoComplete="email"
          required
        />

        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Create a password"
          autoComplete="new-password"
          required
        />

        {error && <p className="form-error">{error}</p>}

        <button className="primary-button" disabled={submitting}>
          {submitting ? "Creating account..." : "Create account"}
        </button>

        <p className="form-footer">
          Already registered? <Link to="/login">Log in</Link>
        </p>
      </form>
    </main>
  );
}

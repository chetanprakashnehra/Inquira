
import {
  createContext,
  useContext,
  useEffect,
  useState,
} from "react";

import { apiRequest } from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadUser() {
      const token = localStorage.getItem("access_token");

      if (!token) {
        setLoading(false);
        return;
      }

      try {
        const currentUser = await apiRequest("/auth/me");
        setUser(currentUser);
      } catch {
        localStorage.removeItem("access_token");
        setUser(null);
      } finally {
        setLoading(false);
      }
    }

    loadUser();
  }, []);

  async function login(email, password) {
    const formData = new URLSearchParams();
    formData.set("username", email);
    formData.set("password", password);

    const result = await apiRequest("/auth/login", {
      method: "POST",
      body: formData,
    });

    localStorage.setItem("access_token", result.access_token);

    try {
      const currentUser = await apiRequest("/auth/me");
      setUser(currentUser);
      return currentUser;
    } catch (error) {
      localStorage.removeItem("access_token");
      throw error;
    }
  }

  async function signup(email, password, fullName) {
    return apiRequest("/auth/signup", {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
        full_name: fullName || null,
      }),
    });
  }

  function logout() {
    localStorage.removeItem("access_token");
    setUser(null);
  }

  return (
    <AuthContext.Provider
      value={{ user, loading, login, signup, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

import { createContext, useContext, useState, useEffect, useCallback, createElement } from "react";
import type { ReactNode } from "react";

export interface User {
  id: string;
  email: string;
  created_at?: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(localStorage.getItem("token"));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const clearError = useCallback(() => setError(null), []);

  const fetchCurrentUser = useCallback(async (authToken: string) => {
    try {
      const res = await fetch("http://localhost:8000/api/auth/me", {
        headers: {
          Authorization: `Bearer ${authToken}`,
        },
      });

      if (res.ok) {
        const userData = await res.json();
        setUser(userData);
      } else {
        // Token might be expired or invalid
        localStorage.removeItem("token");
        setToken(null);
        setUser(null);
      }
    } catch (err) {
      console.error("Failed to fetch user profiles:", err);
      // Don't log out on generic network errors to preserve session, but clear user if appropriate
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (token) {
      fetchCurrentUser(token);
    } else {
      setLoading(false);
    }
  }, [token, fetchCurrentUser]);

  const login = useCallback(async (email: string, password: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("http://localhost:8000/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Login failed");
      }

      localStorage.setItem("token", data.access_token);
      setToken(data.access_token);
      setUser(data.user);
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : "An error occurred during login";
      setError(errMsg);
      throw new Error(errMsg);
    } finally {
      setLoading(false);
    }
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("http://localhost:8000/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Registration failed");
      }

      localStorage.setItem("token", data.access_token);
      setToken(data.access_token);
      setUser(data.user);
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : "An error occurred during registration";
      setError(errMsg);
      throw new Error(errMsg);
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
    setError(null);
  }, []);

  return createElement(
    AuthContext.Provider,
    {
      value: {
        user,
        token,
        loading,
        error,
        login,
        register,
        logout,
        clearError,
      },
    },
    children
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

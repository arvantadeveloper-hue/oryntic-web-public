import React, { createContext, useContext, useEffect, useState } from "react";
import { api, setAuthToken, getToken } from "../lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (!token) { setLoading(false); return; }
    api.get("/auth/me")
      .then((r) => setUser(r.data))
      .catch(() => setAuthToken(null))
      .finally(() => setLoading(false));
  }, []);

  const login = async (email, password) => {
    const r = await api.post("/auth/login", { email, password });
    setAuthToken(r.data.access_token);
    setUser(r.data.user);
    return r.data.user;
  };

  const register = async (email, password, name) => {
    const r = await api.post("/auth/register", { email, password, name });
    setAuthToken(r.data.access_token);
    setUser(r.data.user);
    return r.data.user;
  };

  const logout = () => { setAuthToken(null); setUser(null); };

  const refreshUser = async () => {
    try { const r = await api.get("/auth/me"); setUser(r.data); return r.data; } catch (e) {}
  };

  const setCredits = (c) => setUser((u) => (u ? { ...u, credits: c } : u));

  return (
    <AuthContext.Provider value={{ user, setUser, loading, login, register, logout, refreshUser, setCredits }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);

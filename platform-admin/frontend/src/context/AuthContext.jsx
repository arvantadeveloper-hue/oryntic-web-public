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

  // every auth payload is followed by /auth/me so credit gauges (credits_cap, daily_used) are in sync from the first screen
  const syncMe = () => api.get("/auth/me").then((r) => setUser(r.data)).catch(() => {});

  const login = async (email, password) => {
    const r = await api.post("/auth/login", { email, password });
    setAuthToken(r.data.access_token);
    setUser(r.data.user);
    syncMe();
    return r.data.user;
  };

  const register = async (email, password, name) => {
    const r = await api.post("/auth/register", { email, password, name, app_url: window.location.origin });
    if (r.data.access_token) { setAuthToken(r.data.access_token); setUser(r.data.user); syncMe(); }
    return r.data;
  };

  // apply a {access_token, user} payload (email verification, invite acceptance, workspace switch)
  const applyAuth = (data) => { setAuthToken(data.access_token); setUser(data.user); syncMe(); return data.user; };

  const switchWorkspace = async (workspaceId) => applyAuth((await api.post("/auth/switch-workspace", { workspace_id: workspaceId })).data);

  const logout = () => { setAuthToken(null); setUser(null); };

  const refreshUser = async () => {
    try { const r = await api.get("/auth/me"); setUser(r.data); return r.data; } catch (e) {}
  };

  const setCredits = (c) => setUser((u) => (u ? { ...u, credits: c } : u));

  return (
    <AuthContext.Provider value={{ user, setUser, loading, login, register, logout, refreshUser, setCredits, applyAuth, switchWorkspace }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);

import "@/App.css";
import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { I18nProvider } from "./i18n";
import { AppLayout } from "./components/AppLayout";
import Auth from "./pages/Auth";
import Onboarding from "./pages/Onboarding";
import Home from "./pages/Home";
import Personas from "./pages/Personas";
import CreatePersona from "./pages/CreatePersona";
import PersonaDetail from "./pages/PersonaDetail";
import Chat from "./pages/Chat";
import Workspace from "./pages/Workspace";
import TaskDetail from "./pages/TaskDetail";
import Reminders from "./pages/Reminders";
import WalletPage from "./pages/Wallet";
import Profile from "./pages/Profile";
import Admin from "./pages/Admin";
import VerifyEmail from "./pages/VerifyEmail";
import Gallery from "./pages/Gallery";
import Archives from "./pages/Archives";
import SharePage from "./pages/SharePage";
import Friends from "./pages/Friends";
import ResetPassword from "./pages/ResetPassword";
import Calendar from "./pages/Calendar";

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex min-h-screen items-center justify-center mesh-bg text-slate-400">Loading...</div>;
  if (!user) return <Navigate to="/" replace />;
  if (!user.onboarded) return <Navigate to="/onboarding" replace />;
  return children;
}

function AdminOnly({ children, platform = false }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex min-h-screen items-center justify-center mesh-bg text-slate-400">Loading...</div>;
  if (!user) return <Navigate to="/" replace />;
  if (user.role !== "admin" || (platform && !user.is_platform_admin)) return <Navigate to="/home" replace />;
  return children;
}

function Gate() {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex min-h-screen items-center justify-center mesh-bg text-slate-400">Loading...</div>;
  if (user) return <Navigate to={user.onboarded ? "/home" : "/onboarding"} replace />;
  return <Auth />;
}

function App() {
  return (
    <div className="App">
      <I18nProvider>
        <AuthProvider>
          <BrowserRouter>
            <Toaster position="top-center" theme="dark" richColors />
            <ErrorBoundary>
            <Routes>
              <Route path="/" element={<Gate />} />
              <Route path="/onboarding" element={<Onboarding />} />
              <Route path="/verify-email" element={<VerifyEmail />} />
              <Route path="/reset-password" element={<ResetPassword />} />
              <Route path="/s/:code" element={<SharePage />} />
              <Route element={<Protected><AppLayout /></Protected>}>
                <Route path="/home" element={<Home />} />
                <Route path="/personas" element={<AdminOnly><Personas /></AdminOnly>} />
                <Route path="/personas/new" element={<AdminOnly><CreatePersona /></AdminOnly>} />
                <Route path="/personas/:id" element={<AdminOnly><PersonaDetail /></AdminOnly>} />
                <Route path="/chat" element={<Chat />} />
                <Route path="/chat/:id" element={<Chat />} />
                <Route path="/workspace" element={<Workspace />} />
                <Route path="/workspace/:id" element={<TaskDetail />} />
                <Route path="/reminders" element={<Reminders />} />
                <Route path="/calendar" element={<Calendar />} />
                <Route path="/gallery" element={<Gallery />} />
                <Route path="/archives" element={<Archives />} />
                <Route path="/friends" element={<Friends />} />
                <Route path="/wallet" element={<AdminOnly><WalletPage /></AdminOnly>} />
                <Route path="/profile" element={<Profile />} />
                <Route path="/admin" element={<AdminOnly platform><Admin /></AdminOnly>} />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
            </ErrorBoundary>
          </BrowserRouter>
        </AuthProvider>
      </I18nProvider>
    </div>
  );
}

export default App;

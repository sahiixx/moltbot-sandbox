import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation, Navigate } from "react-router-dom";
import LoginPage from "@/pages/LoginPage";
import SetupPage from "@/pages/SetupPage";
import HubPage from "@/pages/HubPage";
import ChatPage from "@/pages/ChatPage";
import AuthCallback from "@/pages/AuthCallback";
import ModelComparePage from "@/pages/ModelComparePage";
import AnalyticsPage from "@/pages/AnalyticsPage";
import { Toaster } from "@/components/ui/sonner";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH

function AppRouter() {
  const location = useLocation();
  
  // Check URL fragment (not query params) for session_id - MUST be synchronous
  // This runs BEFORE ProtectedRoute to prevent race conditions
  if (location.hash?.includes('session_id=')) {
    return <AuthCallback />;
  }
  
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<SetupPage />} />
      <Route path="/hub" element={<HubPage />} />
      <Route path="/hub/compare" element={<ModelComparePage />} />
      <Route path="/hub/analytics" element={<AnalyticsPage />} />
      <Route path="/chat" element={<ChatPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <div className="App dark">
      <Toaster data-testid="global-toaster" richColors position="top-center" />
      <BrowserRouter>
        <AppRouter />
      </BrowserRouter>
    </div>
  );
}

export default App;

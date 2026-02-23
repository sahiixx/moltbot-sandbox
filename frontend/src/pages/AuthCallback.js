import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Lock, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH

export default function AuthCallback() {
  const navigate = useNavigate();
  const hasProcessed = useRef(false);
  const [accessDenied, setAccessDenied] = useState(null);

  useEffect(() => {
    // Use ref to prevent double processing (StrictMode)
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const processAuth = async () => {
      try {
        // Extract session_id from URL fragment
        const hash = window.location.hash;
        const params = new URLSearchParams(hash.replace('#', ''));
        const sessionId = params.get('session_id');

        if (!sessionId) {
          console.error('No session_id in URL');
          navigate('/login', { replace: true });
          return;
        }

        // Exchange session_id for session
        const response = await fetch(`${API}/auth/session`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ session_id: sessionId })
        });

        if (!response.ok) {
          const error = await response.json().catch(() => ({}));
          console.error('Auth failed:', error);
          
          // Check if this is an instance lock error (403)
          if (response.status === 403 && error.detail) {
            setAccessDenied(error.detail);
            return;
          }
          
          navigate('/login', { replace: true });
          return;
        }

        const data = await response.json();
        
        // Clear the hash from URL and navigate to dashboard with user data
        window.history.replaceState(null, '', window.location.pathname);
        navigate('/', { replace: true, state: { user: data.user } });
        
      } catch (error) {
        console.error('Auth callback error:', error);
        navigate('/login', { replace: true });
      }
    };

    processAuth();
  }, [navigate]);

  // Show access denied screen if instance is locked
  if (accessDenied) {
    return (
      <div className="min-h-screen bg-[#0f0f10] flex items-center justify-center p-4">
        <div className="max-w-md w-full text-center">
          <div className="rounded-lg border border-red-900/60 bg-red-950/40 text-red-300 px-6 py-6">
            <div className="flex items-center justify-center gap-2 mb-4">
              <Lock className="w-6 h-6" />
              <span className="font-semibold text-lg">Access Denied</span>
            </div>
            <p className="text-red-400/90 mb-6">
              {accessDenied}
            </p>
            <Button
              onClick={() => navigate('/login', { replace: true })}
              variant="outline"
              className="border-red-800 text-red-300 hover:bg-red-950/50"
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Login
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0f0f10] flex items-center justify-center">
      <div className="text-zinc-400 flex items-center gap-2">
        <Loader2 className="w-5 h-5 animate-spin" />
        Signing you in...
      </div>
    </div>
  );
}

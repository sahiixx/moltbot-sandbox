import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Loader2, Lock } from 'lucide-react';
import OpenClaw from '@/components/ui/icons/OpenClaw';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

export default function LoginPage() {
  const navigate = useNavigate();
  const [checking, setChecking] = useState(true);
  const [instanceLock, setInstanceLock] = useState(null);

  // Check if already authenticated and instance lock status
  useEffect(() => {
    const checkAuth = async () => {
      try {
        // Check instance lock status first
        const instanceRes = await fetch(`${API}/auth/instance`);
        if (instanceRes.ok) {
          const instanceData = await instanceRes.json();
          setInstanceLock(instanceData);
        }

        const response = await fetch(`${API}/auth/me`, {
          credentials: 'include'
        });
        if (response.ok) {
          // Already authenticated, go to setup
          navigate('/', { replace: true });
          return;
        }
      } catch (e) {
        // Not authenticated
      }
      setChecking(false);
    };
    checkAuth();
  }, [navigate]);

  const handleLogin = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + '/';
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  if (checking) {
    return (
      <div className="min-h-screen bg-[#0f0f10] flex items-center justify-center">
        <div className="text-zinc-400 flex items-center gap-2">
          <Loader2 className="w-5 h-5 animate-spin" />
          Checking authentication...
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0f0f10] text-zinc-100 flex items-center justify-center p-4">
      {/* Subtle texture overlay */}
      <div className="texture-noise" aria-hidden="true" />

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="w-full max-w-md"
      >
        <Card className="border-[#1f2022] bg-[#141416]/95 backdrop-blur-sm">
          <CardHeader className="text-center space-y-4">
            <div className="flex items-center justify-center gap-3">
              <OpenClaw size={48} />
            </div>
            <CardTitle className="heading text-2xl font-semibold">
              OpenClaw Setup
            </CardTitle>
            <CardDescription className="text-zinc-400">
              {instanceLock?.locked 
                ? 'This is a private instance. Only the owner can sign in.'
                : 'Sign in with Google to configure and access your personal OpenClaw instance.'
              }
            </CardDescription>
          </CardHeader>
          
          <CardContent className="space-y-6">
            {instanceLock?.locked ? (
              <div className="space-y-4">
                <div className="rounded-lg border border-red-900/60 bg-red-950/40 text-red-300 px-4 py-4 text-sm">
                  <div className="flex items-center gap-2 mb-2">
                    <Lock className="w-4 h-4" />
                    <span className="font-medium">Private Instance</span>
                  </div>
                  <p className="text-red-400/80">
                    This OpenClaw instance is private and access is restricted.
                  </p>
                </div>
                <button
                  onClick={handleLogin}
                  className="text-xs text-zinc-600 hover:text-zinc-400 underline underline-offset-2"
                >
                  Instance owner? Sign in here
                </button>
              </div>
            ) : (
              <>
                <Button
                  onClick={handleLogin}
                  data-testid="google-login-button"
                  className="w-full bg-white hover:bg-gray-100 text-gray-800 font-medium h-12 flex items-center justify-center gap-3"
                >
                  <svg className="w-5 h-5" viewBox="0 0 24 24">
                    <path
                      fill="currentColor"
                      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                    />
                    <path
                      fill="currentColor"
                      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                    />
                    <path
                      fill="currentColor"
                      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                    />
                    <path
                      fill="currentColor"
                      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                    />
                  </svg>
                  Sign in with Google
                </Button>
                
                <p className="text-xs text-zinc-500 text-center">
                  Your OpenClaw instance will be private and only accessible by you.
                </p>
              </>
            )}
          </CardContent>
        </Card>
        
        <p className="text-xs text-zinc-600 text-center mt-6">
          Powered by{' '}
          <a
            href="https://github.com/openclaw/openclaw"
            target="_blank"
            rel="noreferrer"
            className="text-zinc-500 hover:text-zinc-400 underline underline-offset-2"
          >
            OpenClaw
          </a>
        </p>
      </motion.div>
    </div>
  );
}

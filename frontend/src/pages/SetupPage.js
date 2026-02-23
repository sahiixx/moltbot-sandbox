import React, { useMemo, useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { Eye, EyeOff, Loader2, ExternalLink, CheckCircle2, LogOut, AlertCircle, User, Send, LayoutGrid, MessageSquare, Smartphone, Bell, BellOff, Play } from 'lucide-react';
import OpenClaw from '@/components/ui/icons/OpenClaw';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

// ===== Daily Digest Card =====
function DigestCard() {
  const [config, setConfig] = useState({ enabled: false, send_time: '08:00' });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    Promise.all([
      fetch(`${API}/digest/config`, { credentials: 'include' }).then(r => r.ok ? r.json() : null),
      fetch(`${API}/digest/history`, { credentials: 'include' }).then(r => r.ok ? r.json() : null),
    ]).then(([cfg, hist]) => {
      if (cfg) setConfig({ enabled: cfg.enabled, send_time: cfg.send_time || '08:00' });
      if (hist) setHistory(hist.history || []);
    }).finally(() => setLoading(false));
  }, []);

  const handleSave = async (newConfig) => {
    setSaving(true);
    try {
      const res = await fetch(`${API}/digest/config`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        credentials: 'include', body: JSON.stringify(newConfig)
      });
      const data = await res.json();
      if (res.ok) {
        setConfig(newConfig);
        toast.success(newConfig.enabled ? `Daily digest set for ${newConfig.send_time} UTC` : 'Daily digest disabled');
      } else {
        toast.error(data.detail || 'Failed to save');
      }
    } catch { toast.error('Failed to save'); }
    finally { setSaving(false); }
  };

  const handleTrigger = async () => {
    setTriggering(true);
    try {
      const res = await fetch(`${API}/digest/trigger`, { method: 'POST', credentials: 'include' });
      const data = await res.json();
      toast[data.ok ? 'success' : 'info'](data.message);
      if (data.ok) {
        const hist = await fetch(`${API}/digest/history`, { credentials: 'include' }).then(r => r.json());
        setHistory(hist.history || []);
      }
    } catch { toast.error('Failed to trigger digest'); }
    finally { setTriggering(false); }
  };

  if (loading) return null;

  return (
    <Card data-testid="digest-card" className="border-[#1f2022] bg-[#141416]/95 backdrop-blur-sm">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#FF4500]/10 border border-[#FF4500]/20 flex items-center justify-center">
              {config.enabled ? <Bell className="w-4 h-4 text-[#FF4500]" /> : <BellOff className="w-4 h-4 text-zinc-500" />}
            </div>
            <div>
              <CardTitle className="text-base font-semibold">Daily Digest</CardTitle>
              <CardDescription className="text-zinc-500 text-sm">
                Neo summarises your day and sends it to Telegram
              </CardDescription>
            </div>
          </div>
          <Badge
            data-testid="digest-status-badge"
            className={config.enabled
              ? 'bg-[#FF4500]/15 text-[#FF4500] border border-[#FF4500]/30 text-xs'
              : 'border-zinc-700 text-zinc-500 text-xs'}
            variant={config.enabled ? undefined : 'outline'}
          >
            {config.enabled ? `Daily · ${config.send_time} UTC` : 'Off'}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Toggle + Time */}
        <div className="flex items-center gap-3">
          <div className="flex-1">
            <Label htmlFor="digestTime" className="text-zinc-400 text-xs mb-1 block">Send time (UTC)</Label>
            <Input
              id="digestTime"
              data-testid="digest-time-input"
              type="time"
              value={config.send_time}
              onChange={e => setConfig(c => ({ ...c, send_time: e.target.value }))}
              disabled={saving}
              className="h-9 text-sm bg-[#0f0f10] border-[#1f2022] focus-visible:ring-[#FF4500] focus-visible:ring-offset-0 w-32"
            />
          </div>
          <div className="flex items-center gap-2 pt-5">
            <button
              data-testid="digest-toggle"
              onClick={() => handleSave({ ...config, enabled: !config.enabled })}
              disabled={saving}
              className={`relative w-11 h-6 rounded-full transition-colors focus:outline-none ${
                config.enabled ? 'bg-[#FF4500]' : 'bg-zinc-700'
              }`}
            >
              <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                config.enabled ? 'translate-x-5' : 'translate-x-0'
              }`} />
            </button>
            <span className="text-xs text-zinc-500">{config.enabled ? 'On' : 'Off'}</span>
          </div>
          <Button
            size="sm"
            data-testid="digest-save-btn"
            onClick={() => handleSave(config)}
            disabled={saving}
            className="h-9 px-4 text-xs bg-[#1f2022] hover:bg-[#2a2a2e] text-zinc-300 border border-[#2a2a2e] mt-5"
          >
            {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Save'}
          </Button>
        </div>

        {/* Send Now */}
        <div className="flex items-center justify-between pt-1 border-t border-[#1f2022]">
          <p className="text-xs text-zinc-500">Trigger a digest right now from the last 24h of chats</p>
          <Button
            size="sm"
            data-testid="digest-trigger-btn"
            onClick={handleTrigger}
            disabled={triggering}
            className="h-8 px-3 text-xs bg-[#FF4500] hover:bg-[#e03d00] text-white gap-1.5 ml-3 flex-shrink-0"
          >
            {triggering ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <><Play className="w-3 h-3" />Send Now</>
            )}
          </Button>
        </div>

        {/* History */}
        {history.length > 0 && (
          <div className="pt-1">
            <button
              onClick={() => setShowHistory(h => !h)}
              className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
              data-testid="digest-history-toggle"
            >
              {showHistory ? 'Hide' : 'Show'} past digests ({history.length})
            </button>
            {showHistory && (
              <div className="mt-2 space-y-2">
                {history.slice(0, 3).map((d, i) => (
                  <div key={i} className="rounded-lg bg-[#0f0f10] border border-[#1f2022] p-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[10px] text-zinc-600">
                        {new Date(d.sent_at).toLocaleString()}
                      </span>
                      <div className="flex gap-2">
                        <Badge variant="outline" className="text-[10px] px-1.5 py-0 border-zinc-800 text-zinc-600">
                          {d.message_count} msgs
                        </Badge>
                        {d.telegram_sent && (
                          <Badge className="text-[10px] px-1.5 py-0 bg-[#22c55e]/10 text-[#22c55e] border-[#22c55e]/20">
                            Sent
                          </Badge>
                        )}
                      </div>
                    </div>
                    <p className="text-xs text-zinc-400 line-clamp-3 leading-relaxed whitespace-pre-wrap">
                      {d.content.replace(/\*/g, '')}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ===== WhatsApp Card =====
function WhatsAppCard() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/openclaw/whatsapp/status`, { credentials: 'include' })
      .then(r => r.json()).then(setStatus).catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <Card data-testid="whatsapp-card" className="border-[#1f2022] bg-[#141416]/95 backdrop-blur-sm">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#25D366]/10 border border-[#25D366]/20 flex items-center justify-center">
              <Smartphone className="w-4 h-4 text-[#25D366]" />
            </div>
            <div>
              <CardTitle className="text-base font-semibold">WhatsApp</CardTitle>
              <CardDescription className="text-zinc-500 text-sm">
                Send and receive messages via WhatsApp
              </CardDescription>
            </div>
          </div>
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin text-zinc-500" />
          ) : status?.linked ? (
            <Badge data-testid="whatsapp-status-badge" className="bg-[#22c55e]/15 text-[#22c55e] border border-[#22c55e]/30 text-xs">
              Connected
            </Badge>
          ) : (
            <Badge data-testid="whatsapp-status-badge" variant="outline" className="border-zinc-700 text-zinc-500 text-xs">
              Not linked
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {status?.linked ? (
          <div className="flex items-center gap-3 rounded-lg bg-[#22c55e]/5 border border-[#22c55e]/20 px-4 py-3">
            <CheckCircle2 className="w-4 h-4 text-[#22c55e] flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-zinc-200">WhatsApp linked</p>
              {status.phone && <p className="text-xs text-zinc-500">{status.phone}</p>}
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-zinc-400">
              To link WhatsApp, run this command in your terminal — it will print a QR code to scan:
            </p>
            <div className="rounded-lg bg-[#0d0d0f] border border-[#252528] px-4 py-3 font-mono text-xs text-zinc-300 select-all">
              clawdbot whatsapp link
            </div>
            <p className="text-xs text-zinc-600">
              After scanning, OpenClaw will receive and respond to WhatsApp messages just like Telegram.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function SetupPage() {
  const navigate = useNavigate();
  const location = useLocation();
  
  const [user, setUser] = useState(location.state?.user || null);
  const [isAuthenticated, setIsAuthenticated] = useState(location.state?.user ? true : null);
  const [provider, setProvider] = useState('emergent');
  const [apiKey, setApiKey] = useState('');
  const [reveal, setReveal] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState(null);
  const [checkingStatus, setCheckingStatus] = useState(true);
  const [telegramStatus, setTelegramStatus] = useState(null);
  const [telegramToken, setTelegramToken] = useState('');
  const [telegramReveal, setTelegramReveal] = useState(false);
  const [savingTelegram, setSavingTelegram] = useState(false);

  // Check auth on mount (if not passed from AuthCallback)
  useEffect(() => {
    if (location.state?.user) {
      setIsAuthenticated(true);
      setUser(location.state.user);
      checkOpenClawStatus();
      return;
    }
    
    const checkAuth = async () => {
      try {
        const response = await fetch(`${API}/auth/me`, {
          credentials: 'include'
        });
        if (!response.ok) throw new Error('Not authenticated');
        const userData = await response.json();
        setUser(userData);
        setIsAuthenticated(true);
        checkOpenClawStatus();
      } catch (e) {
        setIsAuthenticated(false);
        navigate('/login', { replace: true });
      }
    };
    checkAuth();
  }, [navigate, location.state]);

  const checkOpenClawStatus = async () => {
    setCheckingStatus(true);
    try {
      const res = await fetch(`${API}/openclaw/status`, {
        credentials: 'include'
      });
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
        if (data.running && data.is_owner) {
          toast.success('OpenClaw is already running!');
        }
      }
    } catch (e) {
      console.error('Status check failed:', e);
    } finally {
      setCheckingStatus(false);
    }
    // Also check telegram status
    fetchTelegramStatus();
  };

  const fetchTelegramStatus = async () => {
    try {
      const res = await fetch(`${API}/telegram/status`, { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        setTelegramStatus(data);
      }
    } catch (e) {
      console.error('Telegram status check failed:', e);
    }
  };

  const handleSaveTelegram = async () => {
    if (!telegramToken.trim()) {
      toast.error('Please enter a Telegram bot token');
      return;
    }
    setSavingTelegram(true);
    try {
      const res = await fetch(`${API}/telegram/configure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ bot_token: telegramToken.trim() })
      });
      const data = await res.json();
      if (res.ok) {
        toast.success(`Telegram bot @${data.bot.username} connected!`);
        setTelegramStatus({ connected: true, bot: data.bot });
        setTelegramToken('');
      } else {
        toast.error(data.detail || 'Failed to configure Telegram');
      }
    } catch (e) {
      toast.error('Failed to connect Telegram bot');
    } finally {
      setSavingTelegram(false);
    }
  };

  const stageText = useMemo(() => {
    if (progress < 10) return 'Waiting to start';
    if (progress < 30) return 'Validating configuration...';
    if (progress < 60) return 'Starting OpenClaw services...';
    if (progress < 85) return 'Initializing Control UI...';
    if (progress < 95) return 'Almost ready...';
    return 'Redirecting to Control UI';
  }, [progress]);

  const goToControlUI = async () => {
    try {
      // Fetch the token to pass to the Control UI
      const res = await fetch(`${API}/openclaw/token`, {
        credentials: 'include'
      });
      if (res.ok) {
        const data = await res.json();
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const gatewayWsUrl = `${wsProtocol}//${window.location.host}/api/openclaw/ws`;
        window.location.href = `${API}/openclaw/ui/?gatewayUrl=${encodeURIComponent(gatewayWsUrl)}&token=${encodeURIComponent(data.token)}`;
      } else {
        toast.error('Unable to get access token');
      }
    } catch (e) {
      toast.error('Failed to access Control UI');
    }
  };

  const handleLogout = async () => {
    try {
      await fetch(`${API}/auth/logout`, {
        method: 'POST',
        credentials: 'include'
      });
    } catch (e) {
      // Ignore errors
    }
    navigate('/login', { replace: true });
  };

  const handleStopOpenClaw = async () => {
    try {
      const res = await fetch(`${API}/openclaw/stop`, {
        method: 'POST',
        credentials: 'include'
      });
      if (res.ok) {
        setStatus(null);
        toast.success('OpenClaw stopped');
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(data.detail || 'Failed to stop OpenClaw');
      }
    } catch (e) {
      toast.error('Failed to stop OpenClaw');
    }
  };

  async function start() {
    setError('');
    if (!provider) {
      setError('Please choose a provider.');
      toast.error('Please choose a provider');
      return;
    }
    // Only require API key for non-emergent providers
    if (provider !== 'emergent' && (!apiKey || apiKey.length < 10)) {
      setError('Please enter a valid API key.');
      toast.error('Please enter a valid API key');
      return;
    }

    try {
      setLoading(true);
      setProgress(15);

      // Simulate progress while waiting
      const progressInterval = setInterval(() => {
        setProgress(prev => {
          if (prev < 80) return prev + Math.random() * 10;
          return prev;
        });
      }, 500);

      const payload = { provider };
      if (provider !== 'emergent' && apiKey) {
        payload.apiKey = apiKey;
      }

      const res = await fetch(`${API}/openclaw/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload)
      });

      clearInterval(progressInterval);

      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: 'Startup failed' }));
        throw new Error(data.detail || 'Startup failed');
      }

      const data = await res.json();
      setProgress(95);
      toast.success('OpenClaw started successfully!');
      
      // Build the Control UI URL with token for authentication
      // The Control UI accepts token as a query parameter which it stores in localStorage
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const gatewayWsUrl = `${wsProtocol}//${window.location.host}/api/openclaw/ws`;
      const controlUrl = `${data.controlUrl}?gatewayUrl=${encodeURIComponent(gatewayWsUrl)}&token=${encodeURIComponent(data.token)}`;
      
      // Small delay before redirect
      setTimeout(() => {
        setProgress(100);
        window.location.href = controlUrl;
      }, 1000);

    } catch (e) {
      console.error(e);
      setError(e.message || 'Unable to start OpenClaw');
      toast.error('Startup error: ' + (e.message || 'Unknown error'));
      setLoading(false);
      setProgress(0);
    }
  }

  if (isAuthenticated === null || checkingStatus) {
    return (
      <div className="min-h-screen bg-[#0f0f10] flex items-center justify-center">
        <div className="text-zinc-400 flex items-center gap-2">
          <Loader2 className="w-5 h-5 animate-spin" />
          {isAuthenticated === null ? 'Checking authentication...' : 'Checking OpenClaw status...'}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0f0f10] text-zinc-100">
      {/* Subtle texture overlay */}
      <div className="texture-noise" aria-hidden="true" />

      {/* Header */}
      <header className="relative z-10 container mx-auto px-4 sm:px-6 py-8 sm:py-12">
        <motion.div 
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="flex justify-between items-start"
        >
          <div className="max-w-lg">
            <div className="flex items-center gap-3 mb-2">
              <OpenClaw size={36} />
              <h1 className="heading text-2xl sm:text-3xl font-semibold tracking-tight">
                OpenClaw Setup
              </h1>
            </div>
            <p className="text-zinc-400 text-sm sm:text-base">
              Connect your LLM provider to start the OpenClaw Control UI.
            </p>
          </div>
          
          {/* User info, hub link, and logout */}
          <div className="flex items-center gap-3">
            {user && (
              <div className="flex items-center gap-2 text-sm text-zinc-400">
                {user.picture ? (
                  <img 
                    src={user.picture} 
                    alt={user.name} 
                    className="w-8 h-8 rounded-full"
                  />
                ) : (
                  <User className="w-5 h-5" />
                )}
                <span className="hidden sm:inline">{user.name}</span>
              </div>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/chat')}
              data-testid="chat-nav-button"
              className="text-zinc-400 hover:text-zinc-200 hover:bg-[#1f2022] gap-2"
            >
              <MessageSquare className="w-4 h-4" />
              <span className="hidden sm:inline">Chat</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/hub')}
              data-testid="hub-nav-button"
              className="text-zinc-400 hover:text-zinc-200 hover:bg-[#1f2022] gap-2"
            >
              <LayoutGrid className="w-4 h-4" />
              <span className="hidden sm:inline">AI Hub</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              data-testid="logout-button"
              className="text-zinc-400 hover:text-zinc-200 hover:bg-[#1f2022]"
            >
              <LogOut className="w-4 h-4" />
              <span className="hidden sm:inline ml-2">Logout</span>
            </Button>
          </div>
        </motion.div>
      </header>

      {/* Main Content */}
      <main className="relative z-10 container mx-auto px-4 sm:px-6 pb-16">
        {/* If OpenClaw is running by another user */}
        {status?.running && !status?.is_owner && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
            className="max-w-lg mb-6"
          >
            <Card className="border-yellow-900/40 bg-yellow-950/20 backdrop-blur-sm">
              <CardContent className="pt-6">
                <div className="flex items-center gap-3 text-yellow-500 mb-4">
                  <AlertCircle className="w-5 h-5" />
                  <span className="font-medium">OpenClaw in use</span>
                </div>
                <p className="text-zinc-400 text-sm">
                  Another user is currently using OpenClaw. Please wait for them to stop their session.
                </p>
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* If already running and user is owner, show status card */}
        {status?.running && status?.is_owner && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
            className="max-w-lg mb-6"
          >
            <Card className="border-[#22c55e]/30 bg-[#141416]/95 backdrop-blur-sm">
              <CardContent className="pt-6">
                <div className="flex items-center gap-3 text-[#22c55e] mb-4">
                  <CheckCircle2 className="w-5 h-5" />
                  <span className="font-medium">OpenClaw is running</span>
                </div>
                <p className="text-zinc-400 text-sm mb-4">
                  Provider: <span className="text-zinc-200 capitalize">{status.provider}</span>
                </p>
                <div className="flex gap-3">
                  <Button
                    onClick={goToControlUI}
                    className="flex-1 bg-[#FF4500] hover:bg-[#E63E00] text-white"
                    data-testid="control-ui-redirect"
                  >
                    Open Control UI
                    <ExternalLink className="w-4 h-4 ml-2" />
                  </Button>
                  <Button
                    onClick={handleStopOpenClaw}
                    variant="outline"
                    className="border-zinc-700 hover:bg-zinc-800 text-zinc-300"
                    data-testid="stop-moltbot-button"
                  >
                    Stop
                  </Button>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* Setup Card - show if not running or if user is owner */}
        {(!status?.running || status?.is_owner) && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, delay: 0.1 }}
          >
            <Card className="max-w-lg border-[#1f2022] bg-[#141416]/95 backdrop-blur-sm setup-card">
              <CardHeader>
                <CardTitle className="heading text-xl font-semibold">
                  {status?.running && status?.is_owner ? 'Restart with Different Config' : 'Provider & API Key'}
                </CardTitle>
                <CardDescription className="text-zinc-400">
                  {status?.running && status?.is_owner 
                    ? 'Restart OpenClaw with a different provider or key'
                    : 'Enter your LLM provider credentials to start OpenClaw'
                  }
                </CardDescription>
              </CardHeader>
              
              <CardContent className="space-y-5">
                {/* Provider Select */}
                <div className="space-y-2">
                  <Label htmlFor="provider" className="text-zinc-200">LLM Provider</Label>
                  <Select 
                    onValueChange={(val) => {
                      setProvider(val);
                      if (val === 'emergent') setApiKey('');
                    }} 
                    value={provider}
                    disabled={loading}
                  >
                    <SelectTrigger 
                      id="provider" 
                      data-testid="provider-select"
                      className="bg-[#0f0f10] border-[#1f2022] focus:ring-[#FF4500] focus:ring-offset-0 h-11"
                    >
                      <SelectValue placeholder="Choose provider" />
                    </SelectTrigger>
                    <SelectContent className="bg-[#141416] border-[#1f2022]">
                      <SelectItem value="emergent" className="focus:bg-[#1f2022]">
                        Emergent (Recommended - No key needed)
                      </SelectItem>
                      <SelectItem value="anthropic" className="focus:bg-[#1f2022]">
                        Anthropic (Claude) - Bring your own key
                      </SelectItem>
                      <SelectItem value="openai" className="focus:bg-[#1f2022]">
                        OpenAI (GPT) - Bring your own key
                      </SelectItem>
                    </SelectContent>
                  </Select>
                  {provider === 'emergent' && (
                    <p className="text-xs text-[#22c55e]">
                      Pre-configured with Claude Opus 4.5 and GPT-5.2 - no API key needed
                    </p>
                  )}
                </div>

                {/* API Key Input - Only show for non-emergent providers */}
                {provider !== 'emergent' && (
                  <div className="space-y-2">
                    <Label htmlFor="apiKey" className="text-zinc-200">API Key</Label>
                    <div className="relative">
                      <Input
                        id="apiKey"
                        data-testid="api-key-input"
                        type={reveal ? 'text' : 'password'}
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        disabled={loading}
                        className="pr-20 tracking-wider bg-[#0f0f10] border-[#1f2022] focus-visible:ring-[#FF4500] focus-visible:ring-offset-0 h-11 api-key-input"
                        placeholder={provider === 'openai' ? 'sk-...' : 'sk-ant-...'}
                        aria-describedby="apiKeyHelp"
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        data-testid="reveal-api-key-toggle"
                        onClick={() => setReveal(r => !r)}
                        disabled={loading}
                        className="absolute right-2 top-1/2 -translate-y-1/2 h-8 px-3 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-[#1f2022]"
                      >
                        {reveal ? (
                          <EyeOff className="w-4 h-4" />
                        ) : (
                          <Eye className="w-4 h-4" />
                        )}
                      </Button>
                    </div>
                    <p id="apiKeyHelp" className="text-xs text-zinc-500">
                      Your key is used only to start OpenClaw and is stored securely.
                    </p>
                  </div>
                )}

                {/* Error Alert */}
                {error && (
                  <motion.div
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    role="alert"
                    data-testid="startup-error"
                    className="rounded-lg border border-red-900/60 bg-red-950/40 text-red-300 px-4 py-3 text-sm"
                  >
                    {error}
                  </motion.div>
                )}

                {/* Progress Indicator */}
                {loading && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="space-y-3"
                  >
                    <Progress 
                      value={progress} 
                      data-testid="startup-progress" 
                      className="h-2 bg-[#1f2022]"
                    />
                    <div className="flex items-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin text-[#FF4500]" />
                      <p 
                        className="text-sm text-zinc-400" 
                        data-testid="startup-status-text"
                        aria-live="polite"
                      >
                        {stageText}
                      </p>
                    </div>
                  </motion.div>
                )}
              </CardContent>

              <CardFooter className="flex flex-col sm:flex-row justify-between gap-4 pt-2">
                <Button
                  onClick={start}
                  data-testid="start-moltbot-button"
                  disabled={loading || !provider || (provider !== 'emergent' && !apiKey) || (status?.running && !status?.is_owner)}
                  className="w-full sm:w-auto bg-[#FF4500] hover:bg-[#E63E00] text-white font-medium h-11 px-6 btn-primary"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Starting...
                    </>
                  ) : (
                    'Start OpenClaw'
                  )}
                </Button>
                
                <a
                  href="https://docs.molt.bot/web/control-ui"
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors flex items-center gap-1"
                  data-testid="docs-link"
                >
                  Documentation
                  <ExternalLink className="w-3 h-3" />
                </a>
              </CardFooter>
            </Card>
          </motion.div>
        )}

        {/* Telegram Bot Card */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2, delay: 0.2 }}
          className="max-w-lg mt-6"
        >
          <Card className="border-[#1f2022] bg-[#141416]/95 backdrop-blur-sm">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Send className="w-5 h-5 text-[#2AABEE]" />
                  <CardTitle className="text-base font-semibold">Telegram Bot</CardTitle>
                </div>
                {telegramStatus?.connected ? (
                  <Badge
                    data-testid="telegram-status-badge"
                    className="bg-[#22c55e]/15 text-[#22c55e] border border-[#22c55e]/30 text-xs"
                  >
                    Connected
                  </Badge>
                ) : (
                  <Badge
                    data-testid="telegram-status-badge"
                    variant="outline"
                    className="border-zinc-700 text-zinc-500 text-xs"
                  >
                    Not connected
                  </Badge>
                )}
              </div>
              <CardDescription className="text-zinc-400 text-sm">
                {telegramStatus?.connected
                  ? `@${telegramStatus.bot?.username} is active and listening for messages.`
                  : 'Connect a Telegram bot to receive and send messages via OpenClaw.'}
              </CardDescription>
            </CardHeader>

            <CardContent className="space-y-3">
              {telegramStatus?.connected ? (
                <div
                  data-testid="telegram-bot-info"
                  className="flex items-center gap-3 rounded-lg border border-[#22c55e]/20 bg-[#22c55e]/5 px-4 py-3"
                >
                  <CheckCircle2 className="w-5 h-5 text-[#22c55e] flex-shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-zinc-200">{telegramStatus.bot?.name}</p>
                    <p className="text-xs text-zinc-500">@{telegramStatus.bot?.username}</p>
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  <Label htmlFor="telegramToken" className="text-zinc-300 text-sm">
                    Bot Token
                  </Label>
                  <div className="relative">
                    <Input
                      id="telegramToken"
                      data-testid="telegram-token-input"
                      type={telegramReveal ? 'text' : 'password'}
                      value={telegramToken}
                      onChange={(e) => setTelegramToken(e.target.value)}
                      disabled={savingTelegram}
                      placeholder="1234567890:AABBcc..."
                      className="pr-20 bg-[#0f0f10] border-[#1f2022] focus-visible:ring-[#2AABEE] focus-visible:ring-offset-0 h-10 text-sm"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      data-testid="telegram-token-reveal"
                      onClick={() => setTelegramReveal(r => !r)}
                      disabled={savingTelegram}
                      className="absolute right-2 top-1/2 -translate-y-1/2 h-8 px-3 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-[#1f2022]"
                    >
                      {telegramReveal ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </Button>
                  </div>
                  <p className="text-xs text-zinc-600">
                    Get your token from{' '}
                    <a href="https://t.me/BotFather" target="_blank" rel="noreferrer" className="text-[#2AABEE] hover:underline">
                      @BotFather
                    </a>{' '}
                    on Telegram.
                  </p>
                </div>
              )}
            </CardContent>

            {!telegramStatus?.connected && (
              <CardFooter className="pt-0">
                <Button
                  onClick={handleSaveTelegram}
                  data-testid="save-telegram-button"
                  disabled={savingTelegram || !telegramToken.trim()}
                  className="bg-[#2AABEE] hover:bg-[#1a9bde] text-white font-medium h-9 px-5 text-sm"
                >
                  {savingTelegram ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Connecting...</>
                  ) : (
                    'Connect Bot'
                  )}
                </Button>
              </CardFooter>
            )}
          </Card>
        </motion.div>

        {/* WhatsApp Card */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.2 }}
          className="max-w-lg mt-6"
        >
          <WhatsAppCard />
        </motion.div>

        {/* Daily Digest Card */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.25 }}
          className="max-w-lg mt-6"
        >
          <DigestCard />
        </motion.div>

        {/* Footer Info */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3, delay: 0.3 }}
          className="max-w-lg mt-8 text-center text-xs text-zinc-600"
        >
          <p>
            OpenClaw is an open-source personal AI assistant.{' '}
            <a 
              href="https://github.com/openclaw/moltbot" 
              target="_blank" 
              rel="noreferrer"
              className="text-zinc-500 hover:text-zinc-400 underline underline-offset-2"
              data-testid="help-link"
            >
              Learn more on GitHub
            </a>
          </p>
        </motion.div>
      </main>
    </div>
  );
}

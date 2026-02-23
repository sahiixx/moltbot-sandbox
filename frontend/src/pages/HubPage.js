import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select';
import { toast } from 'sonner';
import {
  ArrowLeft, Search, ExternalLink, CheckCircle2, Loader2, Zap, Eye, EyeOff,
  User, LogOut, MessageSquare, BarChart3, Sparkles
} from 'lucide-react';
import OpenClaw from '@/components/ui/icons/OpenClaw';
import ProviderCard from '@/components/ProviderCard';
import QuickChatDrawer from '@/components/QuickChatDrawer';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

const CATEGORY_COLORS = {
  General: 'bg-zinc-800 text-zinc-300 border-zinc-700',
  Coding: 'bg-blue-950/60 text-blue-300 border-blue-800/40',
  Autonomous: 'bg-orange-950/60 text-orange-300 border-orange-800/40',
  Creative: 'bg-purple-950/60 text-purple-300 border-purple-800/40',
  Research: 'bg-green-950/60 text-green-300 border-green-800/40',
  Writing: 'bg-yellow-950/60 text-yellow-300 border-yellow-800/40',
};

const INDUSTRY_COLORS = {
  Healthcare: '#22c55e', Finance: '#3b82f6', Education: '#a855f7', 'Customer Service': '#f59e0b',
  Cybersecurity: '#ef4444', Legal: '#6366f1', HR: '#ec4899', Hospitality: '#14b8a6',
  Travel: '#0ea5e9', Communication: '#8b5cf6', Marketing: '#f97316', 'Social Media': '#e879f9',
  'Software Dev': '#60a5fa', 'Web Dev': '#34d399', Retail: '#fbbf24', Data: '#38bdf8',
  Research: '#4ade80', Media: '#c084fc', Entertainment: '#fb7185', Food: '#fdba74',
  'Real Estate': '#a3e635', Agriculture: '#86efac', 'AI Research': '#7dd3fc', Productivity: '#fcd34d',
  'Creative Writing': '#f9a8d4',
};

export default function HubPage() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Personas state
  const [personas, setPersonas] = useState([]);
  const [applyingPersona, setApplyingPersona] = useState(null);

  // Agents state
  const [agents, setAgents] = useState([]);
  const [agentSearch, setAgentSearch] = useState('');
  const [selectedIndustry, setSelectedIndustry] = useState('All');
  const [selectedFramework, setSelectedFramework] = useState('All');
  const [industries, setIndustries] = useState([]);
  const [frameworks, setFrameworks] = useState([]);
  const [agentsLoading, setAgentsLoading] = useState(false);

  // Kimi state
  const [kimiKey, setKimiKey] = useState('');
  const [kimiReveal, setKimiReveal] = useState(false);
  const [kimiSaving, setKimiSaving] = useState(false);
  const [kimiConfigured, setKimiConfigured] = useState(false);

  // Providers state
  const [providers, setProviders] = useState({});

  // Quick chat state
  const [quickChatOpen, setQuickChatOpen] = useState(false);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const res = await fetch(`${API}/auth/me`, { credentials: 'include' });
        if (!res.ok) throw new Error('Not authenticated');
        const userData = await res.json();
        setUser(userData);
      } catch {
        navigate('/login', { replace: true });
        return;
      } finally {
        setLoading(false);
      }
    };
    checkAuth();
    fetchPersonas();
    fetchAgents();
    checkKimiConfig();
    fetchProviders();
  }, [navigate]);

  const fetchPersonas = async () => {
    try {
      const res = await fetch(`${API}/hub/personas`, { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        setPersonas(data.personas || []);
      }
    } catch (e) {
      console.error('Failed to fetch personas:', e);
    }
  };

  const fetchAgents = async (q = '', industry = 'All', framework = 'All') => {
    setAgentsLoading(true);
    try {
      const params = new URLSearchParams();
      if (q) params.set('q', q);
      if (industry !== 'All') params.set('industry', industry);
      if (framework !== 'All') params.set('framework', framework);
      const res = await fetch(`${API}/hub/agents?${params}`, { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        setAgents(data.agents || []);
        setIndustries(['All', ...(data.industries || [])]);
        setFrameworks(['All', ...(data.frameworks || [])]);
      }
    } catch (e) {
      console.error('Failed to fetch agents:', e);
    } finally {
      setAgentsLoading(false);
    }
  };

  const checkKimiConfig = async () => {
    try {
      const res = await fetch(`${API}/openclaw/status`, { credentials: 'include' });
      // For now just assume not configured until applied
    } catch { /* ignore */ }
  };

  const fetchProviders = async () => {
    try {
      const res = await fetch(`${API}/hub/providers`, { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        setProviders(data.providers || {});
        // Check if Kimi is configured
        if (data.providers?.kimi) {
          setKimiConfigured(true);
        }
      }
    } catch (e) {
      console.error('Failed to fetch providers:', e);
    }
  };

  const handleApplyPersona = async (personaId) => {
    setApplyingPersona(personaId);
    try {
      const res = await fetch(`${API}/hub/personas/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ persona_id: personaId })
      });
      const data = await res.json();
      if (res.ok) {
        toast.success(`Persona "${data.persona?.name}" applied to Neo!`);
        fetchPersonas();
      } else {
        toast.error(data.detail || 'Failed to apply persona');
      }
    } catch {
      toast.error('Failed to apply persona');
    } finally {
      setApplyingPersona(null);
    }
  };

  const handleSaveKimi = async () => {
    if (!kimiKey.trim()) {
      toast.error('Please enter your Moonshot API key');
      return;
    }
    setKimiSaving(true);
    try {
      const res = await fetch(`${API}/hub/kimi/configure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ api_key: kimiKey.trim() })
      });
      const data = await res.json();
      if (res.ok) {
        toast.success('Kimi/Moonshot provider added!');
        setKimiConfigured(true);
        setKimiKey('');
      } else {
        toast.error(data.detail || 'Failed to configure Kimi');
      }
    } catch {
      toast.error('Failed to configure Kimi');
    } finally {
      setKimiSaving(false);
    }
  };

  const handleLogout = async () => {
    await fetch(`${API}/auth/logout`, { method: 'POST', credentials: 'include' }).catch(() => {});
    navigate('/login', { replace: true });
  };

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchAgents(agentSearch, selectedIndustry, selectedFramework);
    }, 300);
    return () => clearTimeout(timer);
  }, [agentSearch, selectedIndustry, selectedFramework]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0f0f10] flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-zinc-400" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0f0f10] text-zinc-100">
      <div className="texture-noise" aria-hidden="true" />

      {/* Header */}
      <header className="relative z-10 border-b border-[#1f2022] bg-[#0f0f10]/80 backdrop-blur-sm sticky top-0">
        <div className="container mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/')}
              data-testid="hub-back-btn"
              className="text-zinc-400 hover:text-zinc-200 hover:bg-[#1f2022] gap-2"
            >
              <ArrowLeft className="w-4 h-4" />
              Setup
            </Button>
            <div className="h-4 w-px bg-zinc-800" />
            <div className="flex items-center gap-2">
              <OpenClaw size={22} />
              <span className="font-semibold text-zinc-100 text-sm sm:text-base">AI Hub</span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {user && (
              <div className="flex items-center gap-2 text-sm text-zinc-400">
                {user.picture ? (
                  <img src={user.picture} alt={user.name} className="w-7 h-7 rounded-full" />
                ) : (
                  <User className="w-4 h-4" />
                )}
                <span className="hidden sm:inline text-xs">{user.name}</span>
              </div>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/hub/compare')}
              className="text-zinc-400 hover:text-zinc-200 hover:bg-[#1f2022] gap-2"
            >
              <Zap className="w-4 h-4" />
              <span className="hidden sm:inline text-xs">Compare</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/hub/analytics')}
              className="text-zinc-400 hover:text-zinc-200 hover:bg-[#1f2022] gap-2"
            >
              <BarChart3 className="w-4 h-4" />
              <span className="hidden sm:inline text-xs">Analytics</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/chat')}
              data-testid="hub-chat-btn"
              className="text-zinc-400 hover:text-zinc-200 hover:bg-[#1f2022] gap-2"
            >
              <MessageSquare className="w-4 h-4" />
              <span className="hidden sm:inline text-xs">Chat</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              data-testid="hub-logout-btn"
              className="text-zinc-500 hover:text-zinc-200 hover:bg-[#1f2022]"
            >
              <LogOut className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </header>

      {/* Hero */}
      <div className="relative z-10 container mx-auto px-4 sm:px-6 pt-10 pb-6">
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
        >
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mb-2">
            AI Hub
          </h1>
          <p className="text-zinc-400 max-w-xl">
            Switch Neo's persona, explore 500+ agent use cases, and connect additional LLM providers — all in one place.
          </p>
        </motion.div>
      </div>

      {/* Tabs */}
      <div className="relative z-10 container mx-auto px-4 sm:px-6 pb-20">
        <Tabs defaultValue="personas" className="w-full">
          <TabsList
            data-testid="hub-tabs"
            className="bg-[#141416] border border-[#1f2022] mb-8 h-10"
          >
            <TabsTrigger value="personas" data-testid="tab-personas" className="data-[state=active]:bg-[#FF4500] data-[state=active]:text-white text-zinc-400">
              Persona Library
            </TabsTrigger>
            <TabsTrigger value="agents" data-testid="tab-agents" className="data-[state=active]:bg-[#FF4500] data-[state=active]:text-white text-zinc-400">
              Agent Directory
            </TabsTrigger>
            <TabsTrigger value="providers" data-testid="tab-providers" className="data-[state=active]:bg-[#FF4500] data-[state=active]:text-white text-zinc-400">
              LLM Providers
            </TabsTrigger>
          </TabsList>

          {/* ===== PERSONAS TAB ===== */}
          <TabsContent value="personas">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2 }}
            >
              <p className="text-zinc-500 text-sm mb-6">
                Choose Neo's operating style. Inspired by the world's best AI tools — from{' '}
                <a href="https://github.com/sahiixx/system-prompts-and-models-of-ai-tools" target="_blank" rel="noreferrer" className="text-zinc-400 hover:text-zinc-200 underline underline-offset-2">system-prompts-and-models-of-ai-tools</a>.
                Applying a persona updates Neo's <code className="text-xs bg-[#1f2022] px-1 rounded">IDENTITY.md</code>.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {personas.map((persona, i) => (
                  <motion.div
                    key={persona.id}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.2, delay: i * 0.05 }}
                  >
                    <Card
                      data-testid={`persona-card-${persona.id}`}
                      className={`relative border transition-all h-full flex flex-col ${
                        persona.active
                          ? 'border-[#FF4500]/50 bg-[#FF4500]/5'
                          : 'border-[#1f2022] bg-[#141416]/95 hover:border-zinc-700'
                      }`}
                    >
                      {persona.active && (
                        <div className="absolute top-3 right-3">
                          <Badge className="bg-[#FF4500]/20 text-[#FF4500] border border-[#FF4500]/30 text-xs px-2 py-0.5">
                            Active
                          </Badge>
                        </div>
                      )}
                      <CardHeader className="pb-2 pt-4 px-4">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-2xl" role="img">{persona.emoji}</span>
                          <CardTitle className="text-base font-semibold text-zinc-100">{persona.name}</CardTitle>
                        </div>
                        <Badge
                          variant="outline"
                          className={`text-xs w-fit px-2 py-0 ${CATEGORY_COLORS[persona.category] || CATEGORY_COLORS.General}`}
                        >
                          {persona.category}
                        </Badge>
                      </CardHeader>
                      <CardContent className="px-4 pb-4 flex-1 flex flex-col justify-between gap-3">
                        <p className="text-zinc-400 text-sm leading-relaxed">{persona.description}</p>
                        <Button
                          size="sm"
                          data-testid={`apply-persona-${persona.id}`}
                          onClick={() => handleApplyPersona(persona.id)}
                          disabled={persona.active || applyingPersona === persona.id}
                          className={`w-full h-8 text-xs font-medium transition-all ${
                            persona.active
                              ? 'bg-transparent border border-[#FF4500]/30 text-[#FF4500] cursor-default'
                              : 'bg-[#1f2022] hover:bg-[#FF4500] hover:text-white text-zinc-300 border border-[#2a2a2c]'
                          }`}
                        >
                          {applyingPersona === persona.id ? (
                            <><Loader2 className="w-3 h-3 mr-1.5 animate-spin" />Applying...</>
                          ) : persona.active ? (
                            <><CheckCircle2 className="w-3 h-3 mr-1.5" />Active</>
                          ) : (
                            <><Zap className="w-3 h-3 mr-1.5" />Apply to Neo</>
                          )}
                        </Button>
                      </CardContent>
                    </Card>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          </TabsContent>

          {/* ===== AGENTS TAB ===== */}
          <TabsContent value="agents">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2 }}
            >
              <p className="text-zinc-500 text-sm mb-5">
                Explore 35+ curated AI agent projects across industries. Sourced from{' '}
                <a href="https://github.com/sahiixx/500-AI-Agents-Projects" target="_blank" rel="noreferrer" className="text-zinc-400 hover:text-zinc-200 underline underline-offset-2">500-AI-Agents-Projects</a>.
              </p>

              {/* Filters */}
              <div className="flex flex-col sm:flex-row gap-3 mb-6">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                  <Input
                    data-testid="agent-search"
                    placeholder="Search agents..."
                    value={agentSearch}
                    onChange={e => setAgentSearch(e.target.value)}
                    className="pl-9 bg-[#141416] border-[#1f2022] focus-visible:ring-[#FF4500] focus-visible:ring-offset-0 h-9 text-sm"
                  />
                </div>
                <Select value={selectedIndustry} onValueChange={v => setSelectedIndustry(v)}>
                  <SelectTrigger data-testid="industry-filter" className="w-full sm:w-44 bg-[#141416] border-[#1f2022] h-9 text-sm">
                    <SelectValue placeholder="Industry" />
                  </SelectTrigger>
                  <SelectContent className="bg-[#141416] border-[#1f2022]">
                    {industries.map(i => (
                      <SelectItem key={i} value={i} className="focus:bg-[#1f2022] text-sm">{i}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={selectedFramework} onValueChange={v => setSelectedFramework(v)}>
                  <SelectTrigger data-testid="framework-filter" className="w-full sm:w-40 bg-[#141416] border-[#1f2022] h-9 text-sm">
                    <SelectValue placeholder="Framework" />
                  </SelectTrigger>
                  <SelectContent className="bg-[#141416] border-[#1f2022]">
                    {frameworks.map(f => (
                      <SelectItem key={f} value={f} className="focus:bg-[#1f2022] text-sm">{f}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Results count */}
              <div className="text-xs text-zinc-600 mb-4">
                {agentsLoading ? 'Searching...' : `${agents.length} agents found`}
              </div>

              {/* Agent Cards */}
              {agentsLoading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="w-6 h-6 animate-spin text-zinc-500" />
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {agents.map((agent, i) => (
                    <motion.div
                      key={agent.id}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.15, delay: Math.min(i * 0.03, 0.3) }}
                    >
                      <Card
                        data-testid={`agent-card-${agent.id}`}
                        className="border-[#1f2022] bg-[#141416]/95 hover:border-zinc-700 transition-colors h-full flex flex-col"
                      >
                        <CardHeader className="pb-2 pt-3 px-4">
                          <div className="flex items-start justify-between gap-2">
                            <CardTitle className="text-sm font-semibold text-zinc-100 leading-tight">{agent.name}</CardTitle>
                            <a
                              href={agent.github}
                              target="_blank"
                              rel="noreferrer"
                              data-testid={`agent-github-${agent.id}`}
                              className="text-zinc-600 hover:text-zinc-300 flex-shrink-0 mt-0.5 transition-colors"
                              title="View on GitHub"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                          </div>
                          <div className="flex gap-1.5 mt-1.5 flex-wrap">
                            <Badge
                              variant="outline"
                              className="text-xs px-1.5 py-0 border-0 rounded"
                              style={{
                                backgroundColor: (INDUSTRY_COLORS[agent.industry] || '#6b7280') + '20',
                                color: INDUSTRY_COLORS[agent.industry] || '#9ca3af'
                              }}
                            >
                              {agent.industry}
                            </Badge>
                            <Badge variant="outline" className="text-xs px-1.5 py-0 bg-[#1f2022] border-zinc-700 text-zinc-500">
                              {agent.framework}
                            </Badge>
                          </div>
                        </CardHeader>
                        <CardContent className="px-4 pb-3 flex-1">
                          <p className="text-zinc-500 text-xs leading-relaxed">{agent.description}</p>
                        </CardContent>
                      </Card>
                    </motion.div>
                  ))}
                </div>
              )}

              {!agentsLoading && agents.length === 0 && (
                <div className="text-center py-16 text-zinc-600">
                  <Search className="w-8 h-8 mx-auto mb-3 opacity-40" />
                  <p>No agents found. Try different filters.</p>
                </div>
              )}
            </motion.div>
          </TabsContent>

          {/* ===== PROVIDERS TAB ===== */}
          <TabsContent value="providers">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2 }}
              className="max-w-2xl"
            >
              <p className="text-zinc-500 text-sm mb-8">
                Add additional LLM providers to Neo. Each provider integrates directly into OpenClaw.
              </p>

              {/* Existing providers */}
              <div className="mb-8">
                <h2 className="text-sm font-semibold text-zinc-300 mb-3">Built-in Providers</h2>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {[
                    { name: 'Emergent', desc: 'Claude Sonnet 4.5 + GPT-5.2', status: 'active', color: '#FF4500' },
                    { name: 'Anthropic', desc: 'Claude Opus 4.5 (bring your key)', status: 'optional', color: '#cc785c' },
                    { name: 'OpenAI', desc: 'GPT-5.2, GPT-4o (bring your key)', status: 'optional', color: '#10a37f' },
                  ].map(p => (
                    <div
                      key={p.name}
                      data-testid={`provider-card-${p.name.toLowerCase()}`}
                      className="rounded-lg border border-[#1f2022] bg-[#141416] px-4 py-3 flex flex-col gap-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-zinc-200">{p.name}</span>
                        {p.status === 'active' ? (
                          <Badge className="bg-[#22c55e]/15 text-[#22c55e] border border-[#22c55e]/30 text-xs">Active</Badge>
                        ) : (
                          <Badge variant="outline" className="border-zinc-700 text-zinc-600 text-xs">Optional</Badge>
                        )}
                      </div>
                      <p className="text-xs text-zinc-500">{p.desc}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Additional Providers */}
              <div>
                <h2 className="text-sm font-semibold text-zinc-300 mb-3">
                  Add More Providers
                  <Badge variant="outline" className="ml-2 border-zinc-700 text-zinc-500 text-xs font-normal">Expand your model options</Badge>
                </h2>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <ProviderCard providerId="groq" configured={providers.groq?.configured} />
                  <ProviderCard providerId="cohere" configured={providers.cohere?.configured} />
                  <ProviderCard providerId="deepseek" configured={providers.deepseek?.configured} />
                  <ProviderCard providerId="ollama" configured={providers.ollama?.configured} />
                </div>
              </div>

              {/* Kimi/Moonshot */}
              <div className="mt-8">
                <h2 className="text-sm font-semibold text-zinc-300 mb-3">
                  Moonshot / Kimi
                  <Badge variant="outline" className="ml-2 border-zinc-700 text-zinc-500 text-xs font-normal">From kimi-agent-sdk</Badge>
                </h2>
                <Card
                  data-testid="kimi-provider-card"
                  className="border-[#1f2022] bg-[#141416]"
                >
                  <CardHeader className="pb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-[#00B4D8]/10 border border-[#00B4D8]/20 flex items-center justify-center text-sm">
                        🌙
                      </div>
                      <div>
                        <CardTitle className="text-base">Moonshot AI (Kimi)</CardTitle>
                        <CardDescription className="text-zinc-500 text-sm">
                          Kimi models: 8k, 32k, 128k context. OpenAI-compatible API.
                        </CardDescription>
                      </div>
                      {kimiConfigured && (
                        <Badge className="ml-auto bg-[#22c55e]/15 text-[#22c55e] border border-[#22c55e]/30 text-xs">Configured</Badge>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {kimiConfigured ? (
                      <div className="flex items-center gap-3 rounded-lg border border-[#22c55e]/20 bg-[#22c55e]/5 px-4 py-3">
                        <CheckCircle2 className="w-4 h-4 text-[#22c55e] flex-shrink-0" />
                        <div>
                          <p className="text-sm font-medium text-zinc-200">Kimi provider configured</p>
                          <p className="text-xs text-zinc-500">Models: moonshot-v1-8k, moonshot-v1-32k, moonshot-v1-128k are now available in OpenClaw.</p>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="space-y-1.5">
                          <Label htmlFor="kimiKey" className="text-zinc-300 text-sm">Moonshot API Key</Label>
                          <div className="relative">
                            <Input
                              id="kimiKey"
                              data-testid="kimi-api-key-input"
                              type={kimiReveal ? 'text' : 'password'}
                              value={kimiKey}
                              onChange={e => setKimiKey(e.target.value)}
                              disabled={kimiSaving}
                              placeholder="sk-..."
                              className="pr-12 bg-[#0f0f10] border-[#1f2022] focus-visible:ring-[#00B4D8] focus-visible:ring-offset-0 h-10 text-sm"
                            />
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => setKimiReveal(r => !r)}
                              disabled={kimiSaving}
                              className="absolute right-2 top-1/2 -translate-y-1/2 h-7 px-2 text-zinc-400 hover:text-zinc-200 hover:bg-[#1f2022]"
                            >
                              {kimiReveal ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                            </Button>
                          </div>
                          <p className="text-xs text-zinc-600">
                            Get your key at{' '}
                            <a href="https://platform.moonshot.cn" target="_blank" rel="noreferrer" className="text-[#00B4D8] hover:underline">
                              platform.moonshot.cn
                            </a>
                          </p>
                        </div>
                        <Button
                          onClick={handleSaveKimi}
                          data-testid="save-kimi-btn"
                          disabled={kimiSaving || !kimiKey.trim()}
                          className="bg-[#00B4D8] hover:bg-[#0096b8] text-white font-medium h-9 px-5 text-sm"
                        >
                          {kimiSaving ? (
                            <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Connecting...</>
                          ) : 'Add Kimi Provider'}
                        </Button>
                      </>
                    )}

                    {/* Models list */}
                    <div className="rounded-lg border border-[#1f2022] bg-[#0f0f10] p-3 mt-2">
                      <p className="text-xs font-medium text-zinc-400 mb-2">Available Models</p>
                      <div className="space-y-1.5">
                        {[
                          { id: 'moonshot-v1-8k', ctx: '8k context', best: 'Fast responses' },
                          { id: 'moonshot-v1-32k', ctx: '32k context', best: 'Long documents' },
                          { id: 'moonshot-v1-128k', ctx: '128k context', best: 'Very long context' },
                        ].map(m => (
                          <div key={m.id} className="flex items-center justify-between text-xs">
                            <span className="font-mono text-zinc-300">{m.id}</span>
                            <div className="flex gap-2 items-center">
                              <span className="text-zinc-600">{m.ctx}</span>
                              <Badge variant="outline" className="border-zinc-800 text-zinc-600 text-xs px-1.5 py-0">{m.best}</Badge>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </motion.div>
          </TabsContent>
        </Tabs>
      </div>

      {/* Floating Quick Chat Button */}
      <Button
        onClick={() => setQuickChatOpen(true)}
        className="fixed bottom-6 right-6 w-14 h-14 rounded-full bg-[#FF4500] hover:bg-[#FF4500]/90 text-white shadow-lg z-50"
        title="Quick Chat"
      >
        <MessageSquare className="w-5 h-5" />
      </Button>

      {/* Quick Chat Drawer */}
      <QuickChatDrawer open={quickChatOpen} onClose={() => setQuickChatOpen(false)} />
    </div>
  );
}

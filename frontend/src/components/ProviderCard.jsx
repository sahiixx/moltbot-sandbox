import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { CheckCircle2, Loader2, Eye, EyeOff } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

const PROVIDER_INFO = {
  groq: {
    name: 'Groq',
    emoji: '⚡',
    description: 'Lightning-fast inference. Llama 3.3 70B, Mixtral, Gemma 2.',
    color: '#F55036',
    getKeyUrl: 'https://console.groq.com/keys',
    models: [
      { id: 'llama-3.3-70b-versatile', label: 'Llama 3.3 70B', ctx: '128k' },
      { id: 'llama-3.1-70b-versatile', label: 'Llama 3.1 70B', ctx: '128k' },
      { id: 'mixtral-8x7b-32768', label: 'Mixtral 8x7B', ctx: '32k' }
    ]
  },
  cohere: {
    name: 'Cohere',
    emoji: '🧠',
    description: 'Enterprise RAG & generation. Command R+ with 128k context.',
    color: '#D18EE2',
    getKeyUrl: 'https://dashboard.cohere.com/api-keys',
    models: [
      { id: 'command-r-plus', label: 'Command R+', ctx: '128k' },
      { id: 'command-r', label: 'Command R', ctx: '128k' },
      { id: 'command', label: 'Command', ctx: '4k' }
    ]
  },
  deepseek: {
    name: 'DeepSeek',
    emoji: '🤿',
    description: 'Powerful Chinese AI models. Coding & chat specialized.',
    color: '#0084FF',
    getKeyUrl: 'https://platform.deepseek.com/api_keys',
    models: [
      { id: 'deepseek-chat', label: 'DeepSeek Chat', ctx: '64k' },
      { id: 'deepseek-coder', label: 'DeepSeek Coder', ctx: '64k' }
    ]
  },
  ollama: {
    name: 'Ollama',
    emoji: '🦙',
    description: 'Run models locally. No API key needed.',
    color: '#000000',
    getKeyUrl: 'https://ollama.com/download',
    needsUrl: true,
    models: [
      { id: 'llama3.2', label: 'Llama 3.2 (Local)', ctx: '128k' },
      { id: 'mistral', label: 'Mistral (Local)', ctx: '32k' },
      { id: 'qwen2.5', label: 'Qwen 2.5 (Local)', ctx: '128k' }
    ]
  }
};

export default function ProviderCard({ providerId, configured }) {
  const info = PROVIDER_INFO[providerId];
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('http://localhost:11434');
  const [reveal, setReveal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [isConfigured, setIsConfigured] = useState(configured || false);

  const handleSave = async () => {
    if (providerId !== 'ollama' && !apiKey.trim()) {
      toast.error(`Please enter your ${info.name} API key`);
      return;
    }

    setSaving(true);
    try {
      const res = await fetch(`${API}/hub/providers/configure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          provider: providerId,
          api_key: apiKey.trim() || undefined,
          base_url: providerId === 'ollama' ? baseUrl : undefined
        })
      });
      const data = await res.json();
      if (res.ok) {
        toast.success(`${info.name} provider added! Models: ${data.models.join(', ')}`);
        setIsConfigured(true);
        setApiKey('');
      } else {
        toast.error(data.detail || `Failed to configure ${info.name}`);
      }
    } catch {
      toast.error(`Failed to configure ${info.name}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card
      data-testid={`provider-card-${providerId}`}
      className="border-[#1f2022] bg-[#141416]"
    >
      <CardHeader className="pb-3">
        <div className="flex items-center gap-3">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center text-lg border"
            style={{
              backgroundColor: `${info.color}15`,
              borderColor: `${info.color}30`
            }}
          >
            {info.emoji}
          </div>
          <div className="flex-1">
            <CardTitle className="text-base">{info.name}</CardTitle>
            <CardDescription className="text-zinc-500 text-sm">
              {info.description}
            </CardDescription>
          </div>
          {isConfigured && (
            <Badge className="bg-[#22c55e]/15 text-[#22c55e] border border-[#22c55e]/30 text-xs">
              Configured
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {isConfigured ? (
          <div className="flex items-center gap-3 rounded-lg border border-[#22c55e]/20 bg-[#22c55e]/5 px-4 py-3">
            <CheckCircle2 className="w-4 h-4 text-[#22c55e] flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-zinc-200">{info.name} provider configured</p>
              <p className="text-xs text-zinc-500">
                Models: {info.models.map(m => m.id).join(', ')}
              </p>
            </div>
          </div>
        ) : (
          <>
            {providerId === 'ollama' ? (
              <div className="space-y-1.5">
                <Label htmlFor={`${providerId}-url`} className="text-zinc-300 text-sm">
                  Ollama Base URL
                </Label>
                <Input
                  id={`${providerId}-url`}
                  type="text"
                  value={baseUrl}
                  onChange={e => setBaseUrl(e.target.value)}
                  disabled={saving}
                  placeholder="http://localhost:11434"
                  className="bg-[#0f0f10] border-[#1f2022] focus-visible:ring-[#FF4500] focus-visible:ring-offset-0 h-10 text-sm"
                />
                <p className="text-xs text-zinc-600">
                  Install Ollama from{' '}
                  <a href={info.getKeyUrl} target="_blank" rel="noreferrer" className="text-[#FF4500] hover:underline">
                    ollama.com
                  </a>
                </p>
              </div>
            ) : (
              <div className="space-y-1.5">
                <Label htmlFor={`${providerId}-key`} className="text-zinc-300 text-sm">
                  {info.name} API Key
                </Label>
                <div className="relative">
                  <Input
                    id={`${providerId}-key`}
                    type={reveal ? 'text' : 'password'}
                    value={apiKey}
                    onChange={e => setApiKey(e.target.value)}
                    disabled={saving}
                    placeholder="sk-..."
                    className="pr-12 bg-[#0f0f10] border-[#1f2022] focus-visible:ring-[#FF4500] focus-visible:ring-offset-0 h-10 text-sm"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setReveal(r => !r)}
                    disabled={saving}
                    className="absolute right-2 top-1/2 -translate-y-1/2 h-7 px-2 text-zinc-400 hover:text-zinc-200 hover:bg-[#1f2022]"
                  >
                    {reveal ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                  </Button>
                </div>
                <p className="text-xs text-zinc-600">
                  Get your key at{' '}
                  <a href={info.getKeyUrl} target="_blank" rel="noreferrer" style={{ color: info.color }} className="hover:underline">
                    {info.getKeyUrl.replace('https://', '')}
                  </a>
                </p>
              </div>
            )}
            <Button
              onClick={handleSave}
              disabled={saving || (providerId !== 'ollama' && !apiKey.trim())}
              style={{ backgroundColor: info.color }}
              className="hover:opacity-90 text-white font-medium h-9 px-5 text-sm"
            >
              {saving ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Connecting...
                </>
              ) : (
                `Add ${info.name} Provider`
              )}
            </Button>
          </>
        )}

        {/* Models list */}
        <div className="rounded-lg border border-[#1f2022] bg-[#0f0f10] p-3">
          <p className="text-xs font-medium text-zinc-400 mb-2">Available Models</p>
          <div className="space-y-1.5">
            {info.models.map(m => (
              <div key={m.id} className="flex items-center justify-between text-xs">
                <span className="font-mono text-zinc-300">{m.id}</span>
                <Badge variant="outline" className="border-zinc-800 text-zinc-600 text-xs px-1.5 py-0">
                  {m.ctx} context
                </Badge>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

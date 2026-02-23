import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { ArrowLeft, Play, Loader2, Copy, Download, RotateCcw, Settings } from 'lucide-react';
import OpenClaw from '@/components/ui/icons/OpenClaw';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

const AVAILABLE_MODELS = [
  { id: 'emergent-claude/claude-sonnet-4-5', name: 'Claude Sonnet 4.5', emoji: '🧠' },
  { id: 'emergent-gpt/gpt-5.2', name: 'GPT-5.2', emoji: '🤖' },
  { id: 'llama-3.3-70b-versatile', name: 'Llama 3.3 70B', emoji: '⚡' },
  { id: 'deepseek-chat', name: 'DeepSeek Chat', emoji: '🤿' },
];

const PRESET_PROMPTS = {
  coding: {
    name: 'Code Review',
    prompt: 'Review the following code and suggest improvements:\n\n```python\ndef factorial(n):\n    if n == 0:\n        return 1\n    return n * factorial(n-1)\n```'
  },
  writing: {
    name: 'Blog Post',
    prompt: 'Write a compelling blog post introduction about the future of AI in healthcare. Make it engaging and accessible.'
  },
  analysis: {
    name: 'Data Analysis',
    prompt: 'Analyze this dataset and provide key insights:\n\nSales Q1: $150k\nSales Q2: $185k\nSales Q3: $210k\nSales Q4: $195k'
  },
  creative: {
    name: 'Story Writing',
    prompt: 'Write the opening paragraph of a sci-fi short story set on Mars in the year 2157.'
  }
};

export default function PlaygroundPage() {
  const navigate = useNavigate();
  const [prompt, setPrompt] = useState('');
  const [selectedModels, setSelectedModels] = useState([AVAILABLE_MODELS[0].id, AVAILABLE_MODELS[1].id]);
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(1000);
  const [responses, setResponses] = useState({});
  const [loading, setLoading] = useState({});

  const handleRun = async () => {
    if (!prompt.trim()) {
      toast.error('Please enter a prompt');
      return;
    }

    const newResponses = {};
    const newLoading = {};
    
    selectedModels.forEach(model => {
      newLoading[model] = true;
    });
    setLoading(newLoading);
    setResponses({});

    for (const modelId of selectedModels) {
      try {
        const res = await fetch(`${API}/chat/playground`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            model: modelId,
            prompt: prompt,
            temperature: temperature,
            max_tokens: maxTokens
          })
        });

        if (res.ok) {
          const data = await res.json();
          newResponses[modelId] = {
            text: data.response,
            time: data.time || 0,
            tokens: data.tokens || 0
          };
          setResponses(prev => ({ ...prev, ...newResponses }));
        } else {
          newResponses[modelId] = { text: 'Error: Failed to get response', time: 0, tokens: 0 };
          setResponses(prev => ({ ...prev, ...newResponses }));
        }
      } catch (e) {
        console.error(`Playground error for ${modelId}:`, e);
        newResponses[modelId] = { text: 'Error: Request failed', time: 0, tokens: 0 };
        setResponses(prev => ({ ...prev, ...newResponses }));
      } finally {
        setLoading(prev => ({ ...prev, [modelId]: false }));
      }
    }
  };

  const handleCopy = (text) => {
    navigator.clipboard.writeText(text);
    toast.success('Copied to clipboard');
  };

  const handleExport = () => {
    const markdown = `# Playground Results\n\n## Prompt\n${prompt}\n\n` +
      selectedModels.map(modelId => {
        const model = AVAILABLE_MODELS.find(m => m.id === modelId);
        const response = responses[modelId];
        return `## ${model?.name || modelId}\n\n${response?.text || 'No response'}\n\n**Time:** ${response?.time || 0}s | **Tokens:** ${response?.tokens || 0}\n`;
      }).join('\n');

    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'playground-results.md';
    a.click();
    toast.success('Exported to markdown');
  };

  const handleReset = () => {
    setPrompt('');
    setResponses({});
    setTemperature(0.7);
    setMaxTokens(1000);
  };

  const loadPreset = (preset) => {
    setPrompt(PRESET_PROMPTS[preset].prompt);
    toast.success(`Loaded: ${PRESET_PROMPTS[preset].name}`);
  };

  const toggleModel = (modelId) => {
    if (selectedModels.includes(modelId)) {
      if (selectedModels.length > 1) {
        setSelectedModels(selectedModels.filter(id => id !== modelId));
      }
    } else if (selectedModels.length < 4) {
      setSelectedModels([...selectedModels, modelId]);
    }
  };

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
              onClick={() => navigate('/hub')}
              className="text-zinc-400 hover:text-zinc-200 hover:bg-[#1f2022] gap-2"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to Hub
            </Button>
            <div className="h-4 w-px bg-zinc-800" />
            <div className="flex items-center gap-2">
              <OpenClaw size={22} />
              <span className="font-semibold text-zinc-100 text-sm sm:text-base">Model Playground</span>
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={handleExport}
              disabled={Object.keys(responses).length === 0}
              className="border-[#1f2022] text-zinc-400 hover:bg-[#1f2022] hover:text-zinc-200"
            >
              <Download className="w-4 h-4 mr-1.5" />
              Export
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={handleReset}
              className="border-[#1f2022] text-zinc-400 hover:bg-[#1f2022] hover:text-zinc-200"
            >
              <RotateCcw className="w-4 h-4 mr-1.5" />
              Reset
            </Button>
          </div>
        </div>
      </header>

      <div className="relative z-10 container mx-auto px-4 sm:px-6 py-8">
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="mb-6"
        >
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mb-2">
            Model Playground
          </h1>
          <p className="text-zinc-400">
            Test prompts across multiple models simultaneously and compare results.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Controls Sidebar */}
          <div className="lg:col-span-1 space-y-4">
            {/* Model Selection */}
            <Card className="border-[#1f2022] bg-[#141416]">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Settings className="w-4 h-4" />
                  Models
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {AVAILABLE_MODELS.map(model => (
                  <div
                    key={model.id}
                    onClick={() => toggleModel(model.id)}
                    className={`p-2 rounded border cursor-pointer transition-colors ${
                      selectedModels.includes(model.id)
                        ? 'border-[#FF4500]/50 bg-[#FF4500]/5'
                        : 'border-[#1f2022] hover:border-zinc-700'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-sm">{model.emoji}</span>
                      <span className="text-xs text-zinc-300">{model.name}</span>
                    </div>
                  </div>
                ))}
                <p className="text-xs text-zinc-600 mt-2">Select 1-4 models</p>
              </CardContent>
            </Card>

            {/* Parameters */}
            <Card className="border-[#1f2022] bg-[#141416]">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">Parameters</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <Label className="text-xs text-zinc-400">Temperature</Label>
                    <span className="text-xs text-zinc-500">{temperature.toFixed(1)}</span>
                  </div>
                  <Slider
                    value={[temperature]}
                    onValueChange={([v]) => setTemperature(v)}
                    min={0}
                    max={2}
                    step={0.1}
                    className="w-full"
                  />
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <Label className="text-xs text-zinc-400">Max Tokens</Label>
                    <span className="text-xs text-zinc-500">{maxTokens}</span>
                  </div>
                  <Slider
                    value={[maxTokens]}
                    onValueChange={([v]) => setMaxTokens(v)}
                    min={100}
                    max={4000}
                    step={100}
                    className="w-full"
                  />
                </div>
              </CardContent>
            </Card>

            {/* Presets */}
            <Card className="border-[#1f2022] bg-[#141416]">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">Quick Presets</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5">
                {Object.entries(PRESET_PROMPTS).map(([key, preset]) => (
                  <Button
                    key={key}
                    size="sm"
                    variant="outline"
                    onClick={() => loadPreset(key)}
                    className="w-full justify-start border-[#1f2022] text-zinc-400 hover:bg-[#1f2022] hover:text-zinc-200 h-8 text-xs"
                  >
                    {preset.name}
                  </Button>
                ))}
              </CardContent>
            </Card>
          </div>

          {/* Main Content */}
          <div className="lg:col-span-3 space-y-4">
            {/* Prompt Input */}
            <Card className="border-[#1f2022] bg-[#141416]">
              <CardContent className="pt-6">
                <Textarea
                  value={prompt}
                  onChange={e => setPrompt(e.target.value)}
                  placeholder="Enter your prompt here..."
                  className="min-h-[150px] bg-[#0f0f10] border-[#1f2022] focus-visible:ring-[#FF4500] focus-visible:ring-offset-0 resize-none"
                />
                <Button
                  onClick={handleRun}
                  disabled={!prompt.trim() || Object.values(loading).some(l => l)}
                  className="mt-4 bg-[#FF4500] hover:bg-[#FF4500]/90 text-white"
                >
                  {Object.values(loading).some(l => l) ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Running...
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4 mr-2" />
                      Run on {selectedModels.length} model{selectedModels.length > 1 ? 's' : ''}
                    </>
                  )}
                </Button>
              </CardContent>
            </Card>

            {/* Responses */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {selectedModels.map(modelId => {
                const model = AVAILABLE_MODELS.find(m => m.id === modelId);
                const response = responses[modelId];
                const isLoading = loading[modelId];

                return (
                  <Card key={modelId} className="border-[#1f2022] bg-[#141416]">
                    <CardHeader className="pb-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-lg">{model?.emoji}</span>
                          <CardTitle className="text-sm">{model?.name}</CardTitle>
                        </div>
                        {response && (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => handleCopy(response.text)}
                            className="h-7 px-2 text-zinc-500 hover:text-zinc-200 hover:bg-[#1f2022]"
                          >
                            <Copy className="w-3.5 h-3.5" />
                          </Button>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent>
                      {isLoading ? (
                        <div className="flex flex-col items-center justify-center py-12 text-zinc-500">
                          <Loader2 className="w-6 h-6 animate-spin mb-2" />
                          <p className="text-xs">Generating response...</p>
                        </div>
                      ) : response ? (
                        <>
                          <div className="bg-[#0f0f10] rounded-lg p-4 border border-[#1f2022] min-h-[200px] mb-3">
                            <p className="text-sm text-zinc-300 whitespace-pre-wrap">{response.text}</p>
                          </div>
                          <div className="flex gap-3 text-xs text-zinc-600">
                            <Badge variant="outline" className="border-zinc-700 text-zinc-500">
                              {response.time.toFixed(2)}s
                            </Badge>
                            <Badge variant="outline" className="border-zinc-700 text-zinc-500">
                              {response.tokens} tokens
                            </Badge>
                          </div>
                        </>
                      ) : (
                        <div className="flex items-center justify-center py-12 text-zinc-600">
                          <p className="text-xs">Run a prompt to see results</p>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

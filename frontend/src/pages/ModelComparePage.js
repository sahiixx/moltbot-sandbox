import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { ArrowLeft, Zap, DollarSign, Layers, Eye, Code, Image as ImageIcon, MessageSquare } from 'lucide-react';
import OpenClaw from '@/components/ui/icons/OpenClaw';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

const MODEL_DATABASE = [
  // Emergent
  { id: 'emergent-claude/claude-sonnet-4-5', name: 'Claude Sonnet 4.5', provider: 'Emergent', speed: 95, cost: 3, context: 200000, vision: true, functions: true, reasoning: true },
  { id: 'emergent-gpt/gpt-5.2', name: 'GPT-5.2', provider: 'Emergent', speed: 90, cost: 15, context: 128000, vision: true, functions: true, reasoning: true },
  
  // Groq
  { id: 'llama-3.3-70b-versatile', name: 'Llama 3.3 70B', provider: 'Groq', speed: 100, cost: 0.6, context: 128000, vision: false, functions: true, reasoning: false },
  { id: 'mixtral-8x7b-32768', name: 'Mixtral 8x7B', provider: 'Groq', speed: 98, cost: 0.3, context: 32768, vision: false, functions: true, reasoning: false },
  
  // Cohere
  { id: 'command-r-plus', name: 'Command R+', provider: 'Cohere', speed: 70, cost: 3, context: 128000, vision: false, functions: true, reasoning: false },
  { id: 'command-r', name: 'Command R', provider: 'Cohere', speed: 75, cost: 0.5, context: 128000, vision: false, functions: true, reasoning: false },
  
  // DeepSeek
  { id: 'deepseek-chat', name: 'DeepSeek Chat', provider: 'DeepSeek', speed: 80, cost: 0.3, context: 64000, vision: false, functions: true, reasoning: false },
  { id: 'deepseek-coder', name: 'DeepSeek Coder', provider: 'DeepSeek', speed: 82, cost: 0.3, context: 64000, vision: false, functions: true, reasoning: false },
  
  // Moonshot
  { id: 'moonshot-v1-128k', name: 'Kimi 128k', provider: 'Moonshot', speed: 65, cost: 1, context: 128000, vision: false, functions: true, reasoning: false },
  
  // Ollama (Local)
  { id: 'llama3.2', name: 'Llama 3.2 (Local)', provider: 'Ollama', speed: 40, cost: 0, context: 128000, vision: false, functions: true, reasoning: false },
  { id: 'mistral', name: 'Mistral (Local)', provider: 'Ollama', speed: 45, cost: 0, context: 32768, vision: false, functions: true, reasoning: false },
];

export default function ModelComparePage() {
  const navigate = useNavigate();
  const [selectedModels, setSelectedModels] = useState(['emergent-claude/claude-sonnet-4-5', 'emergent-gpt/gpt-5.2']);
  const [filterProvider, setFilterProvider] = useState('All');

  const providers = ['All', ...new Set(MODEL_DATABASE.map(m => m.provider))];

  const filteredModels = filterProvider === 'All' 
    ? MODEL_DATABASE 
    : MODEL_DATABASE.filter(m => m.provider === filterProvider);

  const comparedModels = MODEL_DATABASE.filter(m => selectedModels.includes(m.id));

  const toggleModel = (modelId) => {
    if (selectedModels.includes(modelId)) {
      setSelectedModels(selectedModels.filter(id => id !== modelId));
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
              <span className="font-semibold text-zinc-100 text-sm sm:text-base">Model Comparison</span>
            </div>
          </div>
        </div>
      </header>

      <div className="relative z-10 container mx-auto px-4 sm:px-6 py-8">
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="mb-8"
        >
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mb-2">
            Compare AI Models
          </h1>
          <p className="text-zinc-400">
            Select up to 4 models to compare side-by-side. Speed, cost, context, and capabilities.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Model Selection Sidebar */}
          <div className="lg:col-span-1">
            <Card className="border-[#1f2022] bg-[#141416] sticky top-24">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">Select Models</CardTitle>
                <p className="text-xs text-zinc-500">Up to 4 models</p>
              </CardHeader>
              <CardContent className="space-y-3">
                {/* Provider Filter */}
                <div className="flex flex-wrap gap-1.5">
                  {providers.map(prov => (
                    <Button
                      key={prov}
                      size="sm"
                      variant={filterProvider === prov ? 'default' : 'outline'}
                      onClick={() => setFilterProvider(prov)}
                      className={`h-7 px-2 text-xs ${
                        filterProvider === prov
                          ? 'bg-[#FF4500] hover:bg-[#FF4500]/90 text-white'
                          : 'border-[#1f2022] text-zinc-400 hover:bg-[#1f2022]'
                      }`}
                    >
                      {prov}
                    </Button>
                  ))}
                </div>

                {/* Model List */}
                <div className="space-y-2 max-h-[500px] overflow-y-auto">
                  {filteredModels.map(model => (
                    <div
                      key={model.id}
                      className={`flex items-start gap-2 p-2 rounded border transition-colors cursor-pointer ${
                        selectedModels.includes(model.id)
                          ? 'border-[#FF4500]/50 bg-[#FF4500]/5'
                          : 'border-[#1f2022] hover:border-zinc-700'
                      }`}
                      onClick={() => toggleModel(model.id)}
                    >
                      <Checkbox
                        checked={selectedModels.includes(model.id)}
                        disabled={!selectedModels.includes(model.id) && selectedModels.length >= 4}
                        className="mt-0.5"
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-zinc-200 truncate">{model.name}</p>
                        <p className="text-xs text-zinc-600">{model.provider}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Comparison Table */}
          <div className="lg:col-span-3">
            {comparedModels.length === 0 ? (
              <Card className="border-[#1f2022] bg-[#141416]">
                <CardContent className="py-12 text-center text-zinc-500">
                  <MessageSquare className="w-12 h-12 mx-auto mb-3 opacity-40" />
                  <p>Select models from the left to compare</p>
                </CardContent>
              </Card>
            ) : (
              <div className="overflow-x-auto">
                <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${comparedModels.length}, minmax(200px, 1fr))` }}>
                  {comparedModels.map(model => (
                    <Card key={model.id} className="border-[#1f2022] bg-[#141416]">
                      <CardHeader className="pb-3">
                        <Badge variant="outline" className="w-fit mb-2 text-xs border-zinc-700 text-zinc-500">
                          {model.provider}
                        </Badge>
                        <CardTitle className="text-base">{model.name}</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        {/* Speed */}
                        <div>
                          <div className="flex items-center gap-2 mb-1.5">
                            <Zap className="w-4 h-4 text-yellow-500" />
                            <span className="text-xs font-medium text-zinc-400">Speed</span>
                          </div>
                          <div className="w-full bg-[#1f2022] rounded-full h-2 overflow-hidden">
                            <div
                              className="h-full bg-gradient-to-r from-yellow-500 to-orange-500 transition-all"
                              style={{ width: `${model.speed}%` }}
                            />
                          </div>
                          <p className="text-xs text-zinc-600 mt-1">{model.speed}/100</p>
                        </div>

                        {/* Cost */}
                        <div>
                          <div className="flex items-center gap-2 mb-1.5">
                            <DollarSign className="w-4 h-4 text-green-500" />
                            <span className="text-xs font-medium text-zinc-400">Cost ($/1M tokens)</span>
                          </div>
                          <p className="text-lg font-semibold text-zinc-200">
                            {model.cost === 0 ? 'Free' : `$${model.cost}`}
                          </p>
                          <p className="text-xs text-zinc-600">
                            {model.cost === 0 ? 'Local model' : model.cost < 1 ? 'Very cheap' : model.cost < 5 ? 'Affordable' : 'Premium'}
                          </p>
                        </div>

                        {/* Context */}
                        <div>
                          <div className="flex items-center gap-2 mb-1.5">
                            <Layers className="w-4 h-4 text-blue-500" />
                            <span className="text-xs font-medium text-zinc-400">Context Window</span>
                          </div>
                          <p className="text-lg font-semibold text-zinc-200">
                            {(model.context / 1000).toFixed(0)}k
                          </p>
                          <p className="text-xs text-zinc-600">tokens</p>
                        </div>

                        {/* Capabilities */}
                        <div>
                          <div className="flex items-center gap-2 mb-2">
                            <Eye className="w-4 h-4 text-purple-500" />
                            <span className="text-xs font-medium text-zinc-400">Capabilities</span>
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {model.vision && (
                              <Badge variant="outline" className="text-xs border-purple-700 text-purple-400 bg-purple-950/30">
                                <ImageIcon className="w-3 h-3 mr-1" />
                                Vision
                              </Badge>
                            )}
                            {model.functions && (
                              <Badge variant="outline" className="text-xs border-blue-700 text-blue-400 bg-blue-950/30">
                                <Code className="w-3 h-3 mr-1" />
                                Functions
                              </Badge>
                            )}
                            {model.reasoning && (
                              <Badge variant="outline" className="text-xs border-orange-700 text-orange-400 bg-orange-950/30">
                                <Zap className="w-3 h-3 mr-1" />
                                Reasoning
                              </Badge>
                            )}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

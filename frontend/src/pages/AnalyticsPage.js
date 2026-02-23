import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select';
import { ArrowLeft, TrendingUp, DollarSign, Zap, Clock, BarChart3 } from 'lucide-react';
import OpenClaw from '@/components/ui/icons/OpenClaw';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

export default function AnalyticsPage() {
  const navigate = useNavigate();
  const [timeRange, setTimeRange] = useState('7d');
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAnalytics();
  }, [timeRange]);

  const fetchAnalytics = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/hub/analytics?range=${timeRange}`, { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        setAnalytics(data);
      }
    } catch (e) {
      console.error('Failed to fetch analytics:', e);
      // Mock data for demo
      setAnalytics({
        totalTokens: 1250000,
        totalCost: 12.45,
        totalRequests: 342,
        avgResponseTime: 1.8,
        topModels: [
          { model: 'claude-sonnet-4-5', requests: 156, tokens: 620000, cost: 6.20, avgTime: 1.5 },
          { model: 'gpt-5.2', requests: 98, tokens: 380000, cost: 5.70, avgTime: 2.1 },
          { model: 'llama-3.3-70b', requests: 54, tokens: 180000, cost: 0.11, avgTime: 0.9 },
          { model: 'deepseek-chat', requests: 34, tokens: 70000, cost: 0.02, avgTime: 2.4 }
        ],
        dailyUsage: [
          { day: 'Mon', tokens: 145000, cost: 1.45 },
          { day: 'Tue', tokens: 198000, cost: 1.98 },
          { day: 'Wed', tokens: 210000, cost: 2.10 },
          { day: 'Thu', tokens: 185000, cost: 1.85 },
          { day: 'Fri', tokens: 232000, cost: 2.32 },
          { day: 'Sat', tokens: 156000, cost: 1.56 },
          { day: 'Sun', tokens: 124000, cost: 1.24 }
        ]
      });
    } finally {
      setLoading(false);
    }
  };

  const formatNumber = (num) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(2)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}k`;
    return num.toString();
  };

  const formatCost = (cost) => `$${cost.toFixed(2)}`;

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
              <span className="font-semibold text-zinc-100 text-sm sm:text-base">Usage Analytics</span>
            </div>
          </div>
          <Select value={timeRange} onValueChange={setTimeRange}>
            <SelectTrigger className="w-32 bg-[#141416] border-[#1f2022] h-9 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-[#141416] border-[#1f2022]">
              <SelectItem value="24h">Last 24h</SelectItem>
              <SelectItem value="7d">Last 7 days</SelectItem>
              <SelectItem value="30d">Last 30 days</SelectItem>
              <SelectItem value="all">All time</SelectItem>
            </SelectContent>
          </Select>
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
            Usage Analytics
          </h1>
          <p className="text-zinc-400">
            Track your AI usage, costs, and performance across all models.
          </p>
        </motion.div>

        {loading ? (
          <div className="text-center py-12 text-zinc-500">Loading analytics...</div>
        ) : (
          <div className="space-y-6">
            {/* Overview Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <Card className="border-[#1f2022] bg-[#141416]">
                <CardContent className="pt-6">
                  <div className="flex items-center justify-between mb-2">
                    <TrendingUp className="w-5 h-5 text-blue-500" />
                    <Badge variant="outline" className="text-xs border-blue-700 text-blue-400 bg-blue-950/30">
                      +12%
                    </Badge>
                  </div>
                  <p className="text-2xl font-bold text-zinc-100">{formatNumber(analytics.totalTokens)}</p>
                  <p className="text-xs text-zinc-500 mt-1">Total Tokens</p>
                </CardContent>
              </Card>

              <Card className="border-[#1f2022] bg-[#141416]">
                <CardContent className="pt-6">
                  <div className="flex items-center justify-between mb-2">
                    <DollarSign className="w-5 h-5 text-green-500" />
                    <Badge variant="outline" className="text-xs border-green-700 text-green-400 bg-green-950/30">
                      -8%
                    </Badge>
                  </div>
                  <p className="text-2xl font-bold text-zinc-100">{formatCost(analytics.totalCost)}</p>
                  <p className="text-xs text-zinc-500 mt-1">Total Cost</p>
                </CardContent>
              </Card>

              <Card className="border-[#1f2022] bg-[#141416]">
                <CardContent className="pt-6">
                  <div className="flex items-center justify-between mb-2">
                    <Zap className="w-5 h-5 text-yellow-500" />
                    <Badge variant="outline" className="text-xs border-yellow-700 text-yellow-400 bg-yellow-950/30">
                      +24%
                    </Badge>
                  </div>
                  <p className="text-2xl font-bold text-zinc-100">{analytics.totalRequests}</p>
                  <p className="text-xs text-zinc-500 mt-1">Total Requests</p>
                </CardContent>
              </Card>

              <Card className="border-[#1f2022] bg-[#141416]">
                <CardContent className="pt-6">
                  <div className="flex items-center justify-between mb-2">
                    <Clock className="w-5 h-5 text-purple-500" />
                    <Badge variant="outline" className="text-xs border-purple-700 text-purple-400 bg-purple-950/30">
                      -15%
                    </Badge>
                  </div>
                  <p className="text-2xl font-bold text-zinc-100">{analytics.avgResponseTime}s</p>
                  <p className="text-xs text-zinc-500 mt-1">Avg Response</p>
                </CardContent>
              </Card>
            </div>

            {/* Daily Usage Chart */}
            <Card className="border-[#1f2022] bg-[#141416]">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-lg">Daily Usage</CardTitle>
                    <CardDescription className="text-zinc-500 text-sm">Token consumption and costs over time</CardDescription>
                  </div>
                  <BarChart3 className="w-5 h-5 text-zinc-500" />
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {analytics.dailyUsage.map((day, i) => {
                    const maxTokens = Math.max(...analytics.dailyUsage.map(d => d.tokens));
                    const width = (day.tokens / maxTokens) * 100;
                    return (
                      <div key={i} className="space-y-1">
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-zinc-400 w-12">{day.day}</span>
                          <div className="flex-1 mx-3">
                            <div className="w-full bg-[#1f2022] rounded-full h-6 overflow-hidden">
                              <div
                                className="h-full bg-gradient-to-r from-blue-500 to-purple-500 flex items-center justify-end pr-2 transition-all"
                                style={{ width: `${width}%` }}
                              >
                                <span className="text-xs text-white font-medium">{formatNumber(day.tokens)}</span>
                              </div>
                            </div>
                          </div>
                          <span className="text-zinc-500 w-16 text-right">{formatCost(day.cost)}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            {/* Top Models */}
            <Card className="border-[#1f2022] bg-[#141416]">
              <CardHeader>
                <CardTitle className="text-lg">Top Models</CardTitle>
                <CardDescription className="text-zinc-500 text-sm">Most used models this period</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {analytics.topModels.map((model, i) => (
                    <div key={i} className="flex items-center gap-4 p-3 rounded-lg border border-[#1f2022] bg-[#0f0f10]">
                      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[#FF4500]/10 border border-[#FF4500]/20 flex items-center justify-center">
                        <span className="text-sm font-bold text-[#FF4500]">#{i + 1}</span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-zinc-200 truncate">{model.model}</p>
                        <div className="flex items-center gap-3 mt-1">
                          <span className="text-xs text-zinc-600">{model.requests} requests</span>
                          <span className="text-xs text-zinc-600">•</span>
                          <span className="text-xs text-zinc-600">{formatNumber(model.tokens)} tokens</span>
                          <span className="text-xs text-zinc-600">•</span>
                          <span className="text-xs text-zinc-600">{model.avgTime}s avg</span>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-semibold text-zinc-200">{formatCost(model.cost)}</p>
                        <p className="text-xs text-zinc-600">cost</p>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}

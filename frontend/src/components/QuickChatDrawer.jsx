import React, { useState } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Loader2, Send, Sparkles, X } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

const QUICK_MODELS = [
  { id: 'emergent-claude/claude-sonnet-4-5', name: 'Claude Sonnet 4.5', emoji: '🧠' },
  { id: 'emergent-gpt/gpt-5.2', name: 'GPT-5.2', emoji: '🤖' },
  { id: 'llama-3.3-70b-versatile', name: 'Llama 3.3 70B', emoji: '⚡' },
  { id: 'deepseek-chat', name: 'DeepSeek Chat', emoji: '🤿' },
  { id: 'command-r-plus', name: 'Command R+', emoji: '🧠' },
];

export default function QuickChatDrawer({ open, onClose }) {
  const [selectedModel, setSelectedModel] = useState(QUICK_MODELS[0].id);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setLoading(true);

    try {
      const res = await fetch(`${API}/chat/quick`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          model: selectedModel,
          message: userMessage
        })
      });

      if (res.ok) {
        const data = await res.json();
        setMessages(prev => [...prev, { role: 'assistant', content: data.response, model: data.model }]);
      } else {
        toast.error('Failed to get response');
      }
    } catch (e) {
      console.error('Quick chat error:', e);
      toast.error('Failed to send message');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const clearChat = () => {
    setMessages([]);
  };

  const selectedModelInfo = QUICK_MODELS.find(m => m.id === selectedModel);

  return (
    <Sheet open={open} onOpenChange={onClose}>
      <SheetContent side="right" className="w-full sm:max-w-xl bg-[#0f0f10] border-[#1f2022] p-0 flex flex-col">
        <SheetHeader className="px-6 py-4 border-b border-[#1f2022]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Sparkles className="w-5 h-5 text-[#FF4500]" />
              <div>
                <SheetTitle className="text-zinc-100">Quick Chat</SheetTitle>
                <SheetDescription className="text-zinc-500 text-sm">
                  Test models instantly without leaving the Hub
                </SheetDescription>
              </div>
            </div>
          </div>
        </SheetHeader>

        {/* Model Selector */}
        <div className="px-6 py-3 border-b border-[#1f2022] bg-[#141416]">
          <div className="flex items-center gap-3">
            <span className="text-xs text-zinc-500">Model:</span>
            <Select value={selectedModel} onValueChange={setSelectedModel}>
              <SelectTrigger className="flex-1 bg-[#0f0f10] border-[#1f2022] h-9 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-[#141416] border-[#1f2022]">
                {QUICK_MODELS.map(model => (
                  <SelectItem key={model.id} value={model.id} className="focus:bg-[#1f2022] text-sm">
                    <span className="flex items-center gap-2">
                      <span>{model.emoji}</span>
                      <span>{model.name}</span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {messages.length > 0 && (
              <Button
                size="sm"
                variant="ghost"
                onClick={clearChat}
                className="text-zinc-500 hover:text-zinc-200 hover:bg-[#1f2022]"
              >
                <X className="w-4 h-4" />
              </Button>
            )}
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center text-zinc-600">
              <Sparkles className="w-12 h-12 mb-3 opacity-40" />
              <p className="text-sm">Start a conversation</p>
              <p className="text-xs mt-1">Quick test any model without switching pages</p>
            </div>
          ) : (
            messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[80%] rounded-lg px-4 py-2.5 ${
                    msg.role === 'user'
                      ? 'bg-[#FF4500] text-white'
                      : 'bg-[#141416] border border-[#1f2022] text-zinc-200'
                  }`}
                >
                  {msg.role === 'assistant' && msg.model && (
                    <Badge variant="outline" className="mb-2 text-xs border-zinc-700 text-zinc-500">
                      {QUICK_MODELS.find(m => m.id === msg.model)?.emoji || '🤖'}{' '}
                      {QUICK_MODELS.find(m => m.id === msg.model)?.name || msg.model}
                    </Badge>
                  )}
                  <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
            ))
          )}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-[#141416] border border-[#1f2022] rounded-lg px-4 py-3">
                <Loader2 className="w-4 h-4 animate-spin text-zinc-500" />
              </div>
            </div>
          )}
        </div>

        {/* Input */}
        <div className="px-6 py-4 border-t border-[#1f2022] bg-[#141416]">
          <div className="flex gap-2">
            <Input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Type a message..."
              disabled={loading}
              className="flex-1 bg-[#0f0f10] border-[#1f2022] focus-visible:ring-[#FF4500] focus-visible:ring-offset-0"
            />
            <Button
              onClick={handleSend}
              disabled={!input.trim() || loading}
              className="bg-[#FF4500] hover:bg-[#FF4500]/90 text-white"
            >
              {loading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </Button>
          </div>
          <p className="text-xs text-zinc-600 mt-2">
            {selectedModelInfo && (
              <span>Testing with {selectedModelInfo.emoji} {selectedModelInfo.name}</span>
            )}
          </p>
        </div>
      </SheetContent>
    </Sheet>
  );
}

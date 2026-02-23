import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Plus, Send, Trash2, Loader2, ArrowLeft, MessageSquare,
  LayoutGrid, User, LogOut, ChevronLeft, ChevronRight,
  Copy, Check, Mic, MicOff, Zap
} from 'lucide-react';
import OpenClaw from '@/components/ui/icons/OpenClaw';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

function formatTime(isoStr) {
  if (!isoStr) return '';
  try {
    return new Date(isoStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch { return ''; }
}

// ===== Markdown code block with copy button =====
function CodeBlock({ children, className }) {
  const [copied, setCopied] = useState(false);
  const code = String(children).replace(/\n$/, '');
  const lang = (className || '').replace('language-', '') || 'code';

  const handleCopy = () => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="relative group my-2 rounded-xl overflow-hidden border border-[#2a2a2e]">
      <div className="flex items-center justify-between px-4 py-1.5 bg-[#111113] border-b border-[#2a2a2e]">
        <span className="text-[10px] text-zinc-500 font-mono uppercase tracking-wide">{lang}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors"
          data-testid="copy-code-btn"
        >
          {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="bg-[#0d0d0f] px-4 py-3 overflow-x-auto">
        <code className="text-sm text-zinc-200 font-mono leading-relaxed">{code}</code>
      </pre>
    </div>
  );
}

// ===== Markdown components config =====
const markdownComponents = {
  code({ node, inline, className, children, ...props }) {
    if (inline) {
      return (
        <code className="bg-[#1f2022] text-[#FF6B35] rounded px-1.5 py-0.5 text-xs font-mono" {...props}>
          {children}
        </code>
      );
    }
    return <CodeBlock className={className}>{children}</CodeBlock>;
  },
  p({ children }) {
    return <p className="mb-3 last:mb-0 leading-relaxed">{children}</p>;
  },
  h1({ children }) { return <h1 className="text-lg font-bold mb-2 mt-3 text-zinc-100">{children}</h1>; },
  h2({ children }) { return <h2 className="text-base font-bold mb-2 mt-3 text-zinc-100">{children}</h2>; },
  h3({ children }) { return <h3 className="text-sm font-bold mb-1 mt-2 text-zinc-200">{children}</h3>; },
  ul({ children }) { return <ul className="list-disc pl-5 mb-3 space-y-1 text-zinc-300">{children}</ul>; },
  ol({ children }) { return <ol className="list-decimal pl-5 mb-3 space-y-1 text-zinc-300">{children}</ol>; },
  li({ children }) { return <li className="text-sm leading-relaxed">{children}</li>; },
  blockquote({ children }) {
    return (
      <blockquote className="border-l-2 border-[#FF4500]/50 pl-3 my-2 text-zinc-400 italic text-sm">
        {children}
      </blockquote>
    );
  },
  strong({ children }) { return <strong className="font-semibold text-zinc-100">{children}</strong>; },
  a({ href, children }) {
    return (
      <a href={href} target="_blank" rel="noreferrer"
        className="text-[#FF6B35] hover:underline underline-offset-2">
        {children}
      </a>
    );
  },
  hr() { return <hr className="border-[#252528] my-3" />; },
  table({ children }) {
    return (
      <div className="overflow-x-auto my-3">
        <table className="text-sm w-full border-collapse">{children}</table>
      </div>
    );
  },
  th({ children }) {
    return <th className="border border-[#2a2a2e] px-3 py-1.5 bg-[#111113] text-left text-zinc-300 font-semibold text-xs">{children}</th>;
  },
  td({ children }) {
    return <td className="border border-[#2a2a2e] px-3 py-1.5 text-zinc-400 text-xs">{children}</td>;
  },
};

// ===== Typewriter hook =====
function useTypewriter(fullText, isNew) {
  const [displayed, setDisplayed] = useState('');
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!isNew || !fullText) {
      setDisplayed(fullText || '');
      setDone(true);
      return;
    }
    setDisplayed('');
    setDone(false);
    let i = 0;
    // Adaptive speed: longer text = faster
    const speed = fullText.length > 500 ? 6 : fullText.length > 200 ? 10 : 18;
    const interval = setInterval(() => {
      i += Math.ceil(fullText.length / 120); // advance multiple chars per tick for speed
      if (i >= fullText.length) {
        setDisplayed(fullText);
        setDone(true);
        clearInterval(interval);
      } else {
        setDisplayed(fullText.slice(0, i));
      }
    }, speed);
    return () => clearInterval(interval);
  }, [fullText, isNew]);

  return { displayed, done };
}

// ===== Message bubble =====
function MessageBubble({ msg, isStreaming }) {
  const isUser = msg.role === 'user';
  const { displayed, done } = useTypewriter(
    msg.content,
    !isUser && !!msg._isNew
  );

  const text = isUser ? msg.content : displayed;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      className={`flex gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'} items-end`}
    >
      {/* Avatar */}
      <div className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold
        ${isUser ? 'bg-[#FF4500]/20 text-[#FF4500]' : 'bg-zinc-800 text-zinc-300'}`}>
        {isUser ? 'U' : '🦞'}
      </div>

      {/* Bubble */}
      <div className="max-w-[82%] sm:max-w-[72%]">
        {isUser ? (
          <div className="rounded-2xl rounded-br-sm px-4 py-2.5 bg-[#FF4500] text-white text-sm leading-relaxed whitespace-pre-wrap break-words">
            {text}
          </div>
        ) : (
          <div className="rounded-2xl rounded-bl-sm px-4 py-3 bg-[#1a1a1c] border border-[#252528] text-zinc-200 text-sm">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {text}
            </ReactMarkdown>
            {!done && (
              <span className="inline-block w-1.5 h-4 bg-zinc-400 ml-0.5 animate-pulse rounded-sm align-middle" />
            )}
          </div>
        )}
        <div className={`text-[10px] text-zinc-600 mt-1 px-1 ${isUser ? 'text-right' : 'text-left'}`}>
          {formatTime(msg.created_at)}
        </div>
      </div>
    </motion.div>
  );
}

function SessionItem({ session, active, onClick, onDelete }) {
  return (
    <div
      data-testid={`session-item-${session.session_id}`}
      onClick={onClick}
      className={`group flex items-center gap-2 px-3 py-2.5 rounded-lg cursor-pointer transition-all text-sm
        ${active ? 'bg-[#FF4500]/10 border border-[#FF4500]/20' : 'hover:bg-[#1a1a1c] border border-transparent'}`}
    >
      <MessageSquare className="w-3.5 h-3.5 flex-shrink-0 text-zinc-500" />
      <span className={`flex-1 truncate text-xs ${active ? 'text-zinc-200' : 'text-zinc-400'}`}>
        {session.title || 'New chat'}
      </span>
      <button
        data-testid={`delete-session-${session.session_id}`}
        onClick={e => { e.stopPropagation(); onDelete(session.session_id); }}
        className="opacity-0 group-hover:opacity-100 p-1 rounded text-zinc-600 hover:text-red-400 transition-all"
      >
        <Trash2 className="w-3 h-3" />
      </button>
    </div>
  );
}

// ===== Voice recording hook =====
function useVoiceRecording(onTranscript) {
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      chunksRef.current = [];
      mr.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        setTranscribing(true);
        try {
          const fd = new FormData();
          fd.append('audio', blob, 'recording.webm');
          const res = await fetch(`${API}/chat/transcribe`, {
            method: 'POST', credentials: 'include', body: fd
          });
          const data = await res.json();
          if (res.ok && data.text) onTranscript(data.text);
          else toast.error('Could not transcribe. Try again.');
        } catch { toast.error('Transcription failed'); }
        finally { setTranscribing(false); }
      };
      mr.start();
      mediaRecorderRef.current = mr;
      setRecording(true);
    } catch {
      toast.error('Microphone access denied');
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  };

  return { recording, transcribing, startRecording, stopRecording };
}

export default function ChatPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(searchParams.get('session') || null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [persona, setPersona] = useState(null);

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => { scrollToBottom(); }, [messages]);

  useEffect(() => {
    const init = async () => {
      try {
        const res = await fetch(`${API}/auth/me`, { credentials: 'include' });
        if (!res.ok) throw new Error();
        setUser(await res.json());
      } catch {
        navigate('/login', { replace: true });
        return;
      } finally {
        setLoading(false);
      }
    };
    init();
    fetchSessions();
    fetchActivePersona();
  }, [navigate]);

  useEffect(() => {
    if (activeSessionId) {
      fetchHistory(activeSessionId);
      setSearchParams({ session: activeSessionId });
    } else {
      setMessages([]);
      setSearchParams({});
    }
  }, [activeSessionId]);

  const fetchSessions = async () => {
    try {
      const res = await fetch(`${API}/chat/sessions`, { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        setSessions(data.sessions || []);
      }
    } catch { /* ignore */ }
  };

  const fetchHistory = async (sid) => {
    try {
      const res = await fetch(`${API}/chat/history/${sid}`, { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages || []);
      }
    } catch { /* ignore */ }
  };

  const fetchActivePersona = async () => {
    try {
      const res = await fetch(`${API}/hub/personas`, { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        const active = data.personas?.find(p => p.active);
        setPersona(active || null);
      }
    } catch { /* ignore */ }
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sending) return;

    setInput('');
    setSending(true);

    // Optimistic UI
    const optimisticUser = {
      role: 'user', content: text,
      created_at: new Date().toISOString(), optimistic: true
    };
    setMessages(prev => [...prev, optimisticUser]);

    try {
      const res = await fetch(`${API}/chat/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ session_id: activeSessionId, message: text })
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to send');

      // Set session and reload messages, mark last assistant msg as new
      if (!activeSessionId) {
        setActiveSessionId(data.session_id);
        fetchSessions();
        // Fetch history then mark last as new for typewriter
        const histRes = await fetch(`${API}/chat/history/${data.session_id}`, { credentials: 'include' });
        if (histRes.ok) {
          const histData = await histRes.json();
          const msgs = histData.messages || [];
          if (msgs.length > 0) msgs[msgs.length - 1]._isNew = true;
          setMessages(msgs);
        }
      } else {
        const histRes = await fetch(`${API}/chat/history/${data.session_id}`, { credentials: 'include' });
        if (histRes.ok) {
          const histData = await histRes.json();
          const msgs = histData.messages || [];
          if (msgs.length > 0) msgs[msgs.length - 1]._isNew = true;
          setMessages(msgs);
        }
        fetchSessions();
      }
    } catch (e) {
      toast.error(e.message || 'Failed to send message');
      // Remove optimistic message
      setMessages(prev => prev.filter(m => !m.optimistic));
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleNewChat = () => {
    setActiveSessionId(null);
    setMessages([]);
    inputRef.current?.focus();
  };

  const handleDeleteSession = async (sid) => {
    try {
      await fetch(`${API}/chat/session/${sid}`, { method: 'DELETE', credentials: 'include' });
      setSessions(prev => prev.filter(s => s.session_id !== sid));
      if (activeSessionId === sid) handleNewChat();
      toast.success('Chat deleted');
    } catch {
      toast.error('Failed to delete chat');
    }
  };

  const handleLogout = async () => {
    await fetch(`${API}/auth/logout`, { method: 'POST', credentials: 'include' }).catch(() => {});
    navigate('/login', { replace: true });
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0f0f10] flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-zinc-400" />
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-[#0f0f10] text-zinc-100 overflow-hidden">
      <div className="texture-noise pointer-events-none" aria-hidden="true" />

      {/* ===== SIDEBAR ===== */}
      <AnimatePresence initial={false}>
        {sidebarOpen && (
          <motion.aside
            key="sidebar"
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 256, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="relative z-10 flex-shrink-0 border-r border-[#1f2022] bg-[#0a0a0b] flex flex-col overflow-hidden"
          >
            {/* Sidebar header */}
            <div className="p-4 border-b border-[#1f2022] flex items-center gap-2">
              <OpenClaw size={20} />
              <span className="font-semibold text-sm text-zinc-200 flex-1">Neo Chat</span>
              <button
                onClick={() => setSidebarOpen(false)}
                className="p-1 rounded text-zinc-600 hover:text-zinc-300 hover:bg-[#1f2022]"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
            </div>

            {/* New Chat button */}
            <div className="p-3">
              <Button
                data-testid="new-chat-btn"
                onClick={handleNewChat}
                className="w-full h-9 text-sm bg-[#FF4500] hover:bg-[#e03d00] text-white gap-2"
              >
                <Plus className="w-4 h-4" />
                New Chat
              </Button>
            </div>

            {/* Sessions list */}
            <div className="flex-1 overflow-y-auto px-2 py-1 space-y-0.5">
              {sessions.length === 0 ? (
                <p className="text-xs text-zinc-600 px-3 py-4 text-center">No chats yet</p>
              ) : (
                sessions.map(s => (
                  <SessionItem
                    key={s.session_id}
                    session={s}
                    active={s.session_id === activeSessionId}
                    onClick={() => setActiveSessionId(s.session_id)}
                    onDelete={handleDeleteSession}
                  />
                ))
              )}
            </div>

            {/* Sidebar nav */}
            <div className="p-3 border-t border-[#1f2022] space-y-1">
              <button
                onClick={() => navigate('/')}
                className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-zinc-500 hover:text-zinc-300 hover:bg-[#1f2022] transition-colors"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                Setup
              </button>
              <button
                onClick={() => navigate('/hub')}
                className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-zinc-500 hover:text-zinc-300 hover:bg-[#1f2022] transition-colors"
              >
                <LayoutGrid className="w-3.5 h-3.5" />
                AI Hub
              </button>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      {/* ===== MAIN CHAT AREA ===== */}
      <div className="flex-1 flex flex-col min-w-0">

        {/* Top bar */}
        <header className="relative z-10 flex items-center gap-3 px-4 py-3 border-b border-[#1f2022] bg-[#0f0f10]/80 backdrop-blur-sm">
          {!sidebarOpen && (
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-[#1f2022] transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          )}

          {/* Persona badge */}
          {persona && (
            <div className="flex items-center gap-1.5 text-xs text-zinc-400">
              <span>{persona.emoji}</span>
              <span className="hidden sm:inline">{persona.name}</span>
            </div>
          )}

          <div className="flex-1" />

          {/* User + actions */}
          <div className="flex items-center gap-2">
            {user?.picture ? (
              <img src={user.picture} alt={user.name} className="w-7 h-7 rounded-full" />
            ) : (
              <User className="w-4 h-4 text-zinc-500" />
            )}
            <button
              onClick={handleLogout}
              data-testid="chat-logout-btn"
              className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-[#1f2022] transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
          {messages.length === 0 && !sending && (
            <div className="flex flex-col items-center justify-center h-full text-center gap-4 py-20">
              <div className="text-4xl">🦞</div>
              <div>
                <h2 className="text-lg font-semibold text-zinc-300 mb-1">
                  {persona ? `Neo in ${persona.name} mode` : 'Chat with Neo'}
                </h2>
                <p className="text-zinc-500 text-sm max-w-xs">
                  Ask me anything. I'm your AI assistant, powered by Claude Sonnet.
                </p>
              </div>
              {/* Suggested prompts */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2 max-w-sm w-full">
                {[
                  'What can you help me with?',
                  'Show me your current persona',
                  'What AI agents are available?',
                  'How do I switch your personality?',
                ].map(prompt => (
                  <button
                    key={prompt}
                    data-testid={`suggested-prompt`}
                    onClick={() => { setInput(prompt); inputRef.current?.focus(); }}
                    className="text-left text-xs text-zinc-400 border border-[#1f2022] bg-[#141416] hover:border-zinc-600 hover:text-zinc-200 rounded-lg px-3 py-2.5 transition-all"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <MessageBubble key={`${msg.session_id}-${i}-${msg.role}`} msg={msg} />
          ))}

          {sending && messages[messages.length - 1]?.role === 'user' && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex gap-3 items-end"
            >
              <div className="w-7 h-7 rounded-full bg-zinc-800 flex items-center justify-center text-xs">🦞</div>
              <div className="bg-[#1a1a1c] border border-[#252528] rounded-2xl rounded-bl-sm px-4 py-3 flex gap-1.5 items-center">
                <div className="w-1.5 h-1.5 bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-1.5 h-1.5 bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-1.5 h-1.5 bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </motion.div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div className="relative z-10 border-t border-[#1f2022] bg-[#0f0f10] p-4">
          <div className="flex gap-2 items-end max-w-3xl mx-auto">
            <div className="flex-1 relative">
              <textarea
                ref={inputRef}
                data-testid="chat-input"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={sending}
                placeholder="Message Neo... (Enter to send, Shift+Enter for newline)"
                rows={1}
                className="w-full resize-none rounded-xl bg-[#141416] border border-[#252528] focus:border-[#FF4500]/50 focus:outline-none px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 transition-colors min-h-[48px] max-h-32 overflow-y-auto"
                style={{ lineHeight: '1.5' }}
                onInput={e => {
                  e.target.style.height = 'auto';
                  e.target.style.height = Math.min(e.target.scrollHeight, 128) + 'px';
                }}
              />
            </div>
            <Button
              data-testid="send-message-btn"
              onClick={handleSend}
              disabled={sending || !input.trim()}
              className="flex-shrink-0 h-12 w-12 rounded-xl bg-[#FF4500] hover:bg-[#e03d00] text-white p-0 disabled:opacity-30"
            >
              {sending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </Button>
          </div>
          <p className="text-center text-[10px] text-zinc-700 mt-2">
            Powered by Claude Sonnet · Persona: {persona?.name || 'Neo (Default)'}
          </p>
        </div>
      </div>
    </div>
  );
}

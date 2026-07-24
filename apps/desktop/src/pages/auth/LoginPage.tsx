import React, { useState } from "react";
import { useAuthStore } from "../../stores/authStore";
import { KeyRound, ShieldAlert, User, Cpu } from "lucide-react";

export const LoginPage: React.FC = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { login, error } = useAuthStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;
    setIsSubmitting(true);
    await login(username.trim(), password);
    setIsSubmitting(false);
  };

  return (
    <div className="relative flex items-center justify-center w-screen h-screen bg-[#262b36] overflow-hidden select-none font-sans text-zinc-100">
      {/* Soft Ambient Radial Background Glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-cyan-500/[0.07] rounded-full blur-[160px] pointer-events-none" />

      {/* Pure Centered Login Panel (No outer card container, no border boxes) */}
      <div className="w-full max-w-[340px] px-4 z-10 animate-fade-in">
        {/* Minimalist Branding Header */}
        <div className="flex flex-col items-center text-center mb-8">
          <div className="flex items-center justify-center w-12 h-12 rounded-2xl bg-cyan-500/10 text-cyan-400 mb-3">
            <Cpu size={24} className="animate-pulse" />
          </div>
          <h1 className="text-xl font-extrabold tracking-tight text-white">
            AI-2D-Checker
          </h1>
          <p className="text-[11px] font-medium text-zinc-500 mt-0.5 tracking-wider uppercase">
            Enterprise Compliance Portal
          </p>
        </div>

        {/* Credentials Form */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {error && (
            <div className="flex items-center gap-2 text-red-400 bg-red-500/10 px-3 py-2 rounded-lg text-xs font-semibold animate-fade-in">
              <ShieldAlert size={15} className="shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-bold uppercase tracking-wider text-zinc-400" htmlFor="username">
              Username
            </label>
            <div className="relative flex items-center">
              <User size={15} className="absolute left-3 text-zinc-500 pointer-events-none" />
              <input
                id="username"
                type="text"
                className="w-full py-2.5 pl-9 pr-3 bg-zinc-900/60 border border-zinc-800 rounded-xl text-white placeholder:text-zinc-600 text-xs font-medium focus:outline-none focus:border-cyan-500/60 focus:bg-zinc-900 transition-all"
                placeholder="Username or ID"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={isSubmitting}
                autoFocus
                required
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-bold uppercase tracking-wider text-zinc-400" htmlFor="password">
              Password
            </label>
            <div className="relative flex items-center">
              <KeyRound size={15} className="absolute left-3 text-zinc-500 pointer-events-none" />
              <input
                id="password"
                type="password"
                className="w-full py-2.5 pl-9 pr-3 bg-zinc-900/60 border border-zinc-800 rounded-xl text-white placeholder:text-zinc-600 text-xs font-medium focus:outline-none focus:border-cyan-500/60 focus:bg-zinc-900 transition-all"
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isSubmitting}
                required
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full mt-1 h-10 bg-cyan-400 hover:bg-cyan-300 active:scale-[0.98] text-zinc-950 font-bold text-xs uppercase tracking-wider rounded-xl transition-all duration-150 shadow-[0_0_15px_rgba(0,229,255,0.2)] disabled:opacity-50 cursor-pointer"
          >
            {isSubmitting ? "Authenticating..." : "Sign In"}
          </button>
        </form>

        {/* Minimalist Quick Account Preset Fill Buttons */}
        <div className="mt-8 pt-5 border-t border-zinc-800/60 flex items-center justify-between text-[11px] text-zinc-500">
          <span>Quick fill:</span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => { setUsername("admin"); setPassword("admin123"); }}
              className="px-2.5 py-1 rounded-md bg-zinc-900 hover:bg-zinc-800 hover:text-cyan-400 border border-zinc-800 transition-colors font-mono cursor-pointer"
            >
              admin
            </button>
            <button
              type="button"
              onClick={() => { setUsername("engineer"); setPassword("engineer123"); }}
              className="px-2.5 py-1 rounded-md bg-zinc-900 hover:bg-zinc-800 hover:text-cyan-400 border border-zinc-800 transition-colors font-mono cursor-pointer"
            >
              engineer
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

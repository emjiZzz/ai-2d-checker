import React, { useState } from "react";
import kmtiLogo from "../../assets/kmti_logo.png";
import { useAuthStore } from "../../stores/authStore";
import { KeyRound, ShieldAlert, User, Eye, EyeOff, ArrowRight } from "lucide-react";

export const LoginPage: React.FC = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
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
    <div className="flex flex-col w-full h-full bg-bg-dark overflow-hidden select-none font-sans text-text-primary transition-colors duration-300">
      {/* Main Container */}
      <main className="flex-1 flex flex-col items-center justify-center px-4 py-8 relative">
        {/* Centered Login Card */}
        <div className="w-full max-w-[420px] bg-bg-card rounded-2xl p-8 sm:p-10 shadow-xl border border-border-color z-10 animate-fade-in">
          {/* Logo Header */}
          <div className="flex flex-col items-center text-center mb-8">
            <img src={kmtiLogo} alt="KMTI Logo" className="w-16 h-16 object-contain mb-5 shrink-0" />
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-text-primary mb-1">
              AI-2D-Checker
            </h1>
            <p className="text-[10px] font-bold text-text-muted tracking-widest uppercase">
              Enterprise Compliance Portal
            </p>
          </div>

          {/* Credentials Form */}
          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            {error && (
              <div className="flex items-center gap-2 text-red-500 bg-red-500/10 border border-red-500/20 px-3.5 py-2.5 rounded-xl text-xs font-semibold animate-fade-in">
                <ShieldAlert size={16} className="shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div className="flex flex-col gap-1.5">
              <label className="text-[10px] font-bold uppercase tracking-wider text-text-muted" htmlFor="username">
                Username
              </label>
              <div className="relative flex items-center">
                <User size={16} className="absolute left-4 text-text-muted pointer-events-none" />
                <input
                  id="username"
                  type="text"
                  autoComplete="off"
                  className="w-full py-3.5 pl-11 pr-4 bg-bg-sidebar border border-border-color rounded-xl text-text-primary placeholder:text-text-muted text-xs font-medium focus:outline-none focus:ring-2 focus:ring-accent-cyan/30 focus:border-accent-cyan transition-all"
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
              <label className="text-[10px] font-bold uppercase tracking-wider text-text-muted" htmlFor="password">
                Password
              </label>
              <div className="relative flex items-center">
                <KeyRound size={16} className="absolute left-4 text-text-muted pointer-events-none" />
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="off"
                  className="w-full py-3.5 pl-11 pr-11 bg-bg-sidebar border border-border-color rounded-xl text-text-primary placeholder:text-text-muted text-xs font-medium focus:outline-none focus:ring-2 focus:ring-accent-cyan/30 focus:border-accent-cyan transition-all"
                  placeholder="Enter password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isSubmitting}
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-4 text-text-muted hover:text-text-primary transition-colors cursor-pointer"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full mt-1 py-3.5 bg-accent-cyan hover:brightness-110 active:scale-[0.99] text-on-accent font-bold text-xs uppercase tracking-wider rounded-xl transition-all duration-150 shadow-lg shadow-accent-cyan/20 disabled:opacity-50 cursor-pointer flex items-center justify-center gap-2"
            >
              <span>{isSubmitting ? "Authenticating..." : "SIGN IN"}</span>
              {!isSubmitting && <ArrowRight size={16} />}
            </button>
          </form>

          {/* Quick Fill Accounts */}
          <div className="mt-8 flex items-center justify-center gap-3 text-[11px] text-text-muted">
            <span>Quick fill:</span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => { setUsername("admin"); setPassword("admin123"); }}
                className="px-3 py-1.5 rounded-full bg-bg-sidebar border border-border-color hover:border-accent-cyan/50 hover:text-accent-cyan text-text-secondary transition-colors font-medium cursor-pointer"
              >
                admin
              </button>
              <button
                type="button"
                onClick={() => { setUsername("engineer"); setPassword("engineer123"); }}
                className="px-3 py-1.5 rounded-full bg-bg-sidebar border border-border-color hover:border-accent-cyan/50 hover:text-accent-cyan text-text-secondary transition-colors font-medium cursor-pointer"
              >
                engineer
              </button>
            </div>
          </div>
        </div>

        {/* Bottom Footer */}
        <div className="mt-8 text-[11px] font-medium text-text-muted tracking-wide text-center">
          KMTI Checker · Enterprise Edition
        </div>
      </main>
    </div>
  );
};


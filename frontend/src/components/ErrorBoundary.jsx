import React from "react";
import { RefreshCw } from "lucide-react";

// Prevents a white screen: any render crash shows a friendly recovery card instead.
export class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(error) { return { error }; }
  componentDidCatch(error, info) { console.error("UI crash:", error, info?.componentStack); }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#F6F8FC] p-6" data-testid="error-boundary">
        <div className="max-w-md rounded-2xl bg-white p-6 text-center shadow-xl">
          <p className="text-lg font-bold text-slate-900">Terjadi kesalahan tampilan</p>
          <p className="mt-1 text-sm text-slate-500">Data Anda aman. Muat ulang untuk melanjutkan.</p>
          <p className="mt-2 break-words rounded-lg bg-slate-50 p-2 text-left text-[11px] text-slate-400">{String(this.state.error?.message || this.state.error).slice(0, 300)}</p>
          <button onClick={() => window.location.reload()} data-testid="error-reload" className="btn-primary mt-4"><RefreshCw size={14} /> Muat ulang</button>
        </div>
      </div>
    );
  }
}

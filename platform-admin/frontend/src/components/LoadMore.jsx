import React from "react";
import { Loader2 } from "lucide-react";

export function LoadMore({ onClick, loading, testid = "load-more" }) {
  return (
    <div className="flex justify-center py-3">
      <button onClick={onClick} disabled={loading} data-testid={testid} className="flex items-center gap-2 rounded-full border border-[#E7ECF3] bg-white px-4 py-1.5 text-xs font-semibold text-[#2F6BFF] hover:bg-[#EEF3FF] disabled:opacity-60">{loading && <Loader2 size={12} className="animate-spin" />} Muat lebih banyak</button>
    </div>
  );
}

import React from "react";

const MARK = "https://customer-assets-cm19k8pv.emergentagent.net/job_ai-companion-test-5/artifacts/7x1kdqac_Aivora_Standalone_Mark.png";

export function Logo({ size = 36, showText = true, className = "" }) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`} data-testid="aivora-logo">
      <img src={MARK} alt="Aivora" style={{ width: size, height: size }} className="object-contain drop-shadow-[0_0_12px_rgba(0,209,255,0.4)]" />
      {showText && (
        <span className="text-xl font-extrabold tracking-tight text-white">Aivora</span>
      )}
    </div>
  );
}

export const AIVORA_MARK = MARK;

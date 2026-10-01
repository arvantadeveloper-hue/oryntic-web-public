import React from "react";

export const BRAND_MARK = "/brand/mark-512.png";
export const BRAND_LOGO_DARK = "/brand/logo-dark.webp";
export const BRAND_LOGO_WHITE = "/brand/logo-white.webp";
export const BRAND_HERO = "/brand/mark.png";
export const TAGLINE = "Intelligence, Orchestrated.";

export function Mark({ size = 34, className = "" }) {
  return <img src={BRAND_MARK} width={size} height={size} alt="" className={`shrink-0 object-contain ${className}`} style={{ width: size, height: size }} aria-hidden />;
}

export function Logo({ size = 32, showText = true, light = false, className = "" }) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`} data-testid="oryntix-logo">
      <Mark size={size} />
      {showText && (
        <span className={`text-[22px] font-bold leading-none tracking-tight ${light ? "text-white" : "text-[#0A1128]"}`}>Oryntix</span>
      )}
    </div>
  );
}

export function LogoFull({ light = false, height = 40, className = "" }) {
  return <img src={light ? BRAND_LOGO_WHITE : BRAND_LOGO_DARK} alt="Oryntix — Intelligence, Orchestrated." style={{ height }} className={`object-contain ${className}`} data-testid="oryntix-logo-full" />;
}

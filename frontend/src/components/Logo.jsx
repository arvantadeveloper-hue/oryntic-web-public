import React from "react";

export function Mark({ size = 34, className = "" }) {
  const id = React.useId();
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none" className={className} aria-hidden>
      <defs>
        <linearGradient id={id} x1="6" y1="42" x2="42" y2="6" gradientUnits="userSpaceOnUse">
          <stop stopColor="#22B8FF" />
          <stop offset="0.5" stopColor="#2F6BFF" />
          <stop offset="1" stopColor="#7C3AED" />
        </linearGradient>
      </defs>
      <path d="M9 41 L24 7 L39 41" stroke={`url(#${id})`} strokeWidth="5.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M16.5 29 L31.5 29" stroke={`url(#${id})`} strokeWidth="5.5" strokeLinecap="round" />
    </svg>
  );
}

export function Logo({ size = 34, showText = true, light = false, className = "" }) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`} data-testid="aivora-logo">
      <Mark size={size} />
      {showText && (
        <span className={`text-xl font-extrabold tracking-tight ${light ? "text-white" : "text-slate-900"}`}>Aivora</span>
      )}
    </div>
  );
}

export const AIVORA_HERO = "https://static.prod-images.emergentagent.com/jobs/7c4c21b3-5636-4f0b-a827-715fd3f3daab/images/96f31df5c2fe78cf05217e0aed1fa20a2dc1f53b786ae1ffdfd79f26cdde90b2.jpeg";

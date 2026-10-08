import React, { useState } from "react";
import { MoreVertical, UserPlus, Mic, LayoutGrid } from "lucide-react";
import { Popover, PopoverTrigger, PopoverContent } from "./ui/popover";
import { MicSettingsPanel } from "./MicSettingsMenu";
import { LayoutOptions } from "./MeetingShell";

// "⋮" menu on the call screen: microphone settings, layout and invite in one place.
export function CallMoreMenu({ micPrefs, onMicChange, pipeline, layout, onLayoutChange, onInvite, inviteDisabled }) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState("mic");
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button data-testid="call-more-btn" title="Lainnya: mikrofon, tata letak, undang" className={`flex h-14 w-14 items-center justify-center rounded-full text-white transition ${open ? "bg-white/25" : "bg-white/10 hover:bg-white/20"}`}><MoreVertical size={22} /></button>
      </PopoverTrigger>
      <PopoverContent side="top" align="center" sideOffset={12} className="z-[120] w-80 rounded-2xl border-white/10 bg-[#0f172a] p-3 text-white shadow-2xl" data-testid="call-more-menu">
        <div className="mb-3 flex gap-1 rounded-xl bg-white/5 p-1">
          {[["mic", Mic, "Mikrofon"], ["layout", LayoutGrid, "Tata letak"]].map(([k, Icon, l]) => (
            <button key={k} onClick={() => setTab(k)} data-testid={`call-more-tab-${k}`} className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg py-1.5 text-xs font-semibold transition ${tab === k ? "bg-white/15" : "text-white/60 hover:text-white"}`}><Icon size={13} /> {l}</button>
          ))}
        </div>
        {tab === "mic" && <MicSettingsPanel prefs={micPrefs} onChange={onMicChange} pipeline={pipeline} active={open} />}
        {tab === "layout" && <div data-testid="layout-menu"><LayoutOptions layout={layout} onChange={onLayoutChange} onPicked={() => setOpen(false)} /></div>}
        {onInvite && (
          <button onClick={() => { setOpen(false); onInvite(); }} disabled={inviteDisabled} data-testid="call-invite-btn"
            className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-[#2F6BFF] py-2.5 text-sm font-bold transition hover:brightness-110 disabled:opacity-50"><UserPlus size={16} /> Undang teman / asisten</button>
        )}
      </PopoverContent>
    </Popover>
  );
}

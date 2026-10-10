import React, { useEffect, useState } from "react";
import { api } from "../lib/api";

// "Karakter Persona": platform-managed presets; the default is the built-in Oryntix assistant character.
export function CharacterPicker({ value, onChange, hint = true, testid = "persona-character" }) {
  const [characters, setCharacters] = useState([]);
  useEffect(() => { api.get("/personas/characters").then((r) => setCharacters(r.data.items || [])).catch(() => {}); }, []);
  const current = characters.find((c) => c.id === (value || "default"));
  return (
    <div>
      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">Karakter Persona</label>
      <select className="input-dark py-2.5" value={value || "default"} onChange={(e) => onChange(e.target.value)} data-testid={testid}>
        {characters.length === 0 && <option value="default">Asisten Oryntix (bawaan)</option>}
        {characters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select>
      {hint && current?.description && <p className="mt-1 text-xs text-slate-400" data-testid={`${testid}-desc`}>{current.description}</p>}
    </div>
  );
}

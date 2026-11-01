import { useEffect, useState } from "react";
import { getExperience, setExperience } from "../api/agent";

export default function ExperienceSetting({ onChange }: { onChange?: (l: "beginner" | "experienced" | null) => void }) {
  const [level, setLevel] = useState<"beginner" | "experienced" | null>(null);
  const [remember, setRemember] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { getExperience().then((p) => { setLevel(p.user_level); setRemember(p.remember_level); onChange?.(p.user_level); }).catch(() => undefined); }, []); // eslint-disable-line

  async function save(l: "beginner" | "experienced", r: boolean) {
    setLevel(l); setRemember(r); onChange?.(l);
    try { await setExperience(l, r); setMsg(r ? "Saved for future sessions." : "Used for this session only."); } catch (e) { setMsg((e as Error).message); }
  }
  return (
    <fieldset className="lc-ai"><legend>How should I explain things?</legend>
      <label><input type="radio" name="lvl" checked={level === "beginner"} onChange={() => void save("beginner", remember)} /> Beginner: plain language, one small step at a time</label><br />
      <label><input type="radio" name="lvl" checked={level === "experienced"} onChange={() => void save("experienced", remember)} /> Experienced: short and technical</label><br />
      <label><input type="checkbox" checked={remember} disabled={!level} onChange={(e) => level && void save(level, e.target.checked)} /> Remember this for future sessions</label>
      {msg && <p className="lc-note" role="status">{msg}</p>}
    </fieldset>
  );
}

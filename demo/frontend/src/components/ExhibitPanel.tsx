import { useEffect, useRef, useState, type FormEvent } from "react";
import type { Exhibit } from "../lib/types";

interface Props {
  exhibits: Exhibit[] | null;
  exhibitsError: string | null;
  live: boolean;
  liveReason: string;
  activeId: string | null;
  busy: boolean;
  onPick: (ex: Exhibit) => void;
  onSubmitTyped: (description: string) => void;
  onDescribePhoto: (image: string) => Promise<string>;
}

type Tab = "docket" | "type" | "photo";

export function ExhibitPanel({ exhibits, exhibitsError, live, liveReason, activeId, busy, onPick, onSubmitTyped, onDescribePhoto }: Props) {
  const [tab, setTab] = useState<Tab>("docket");
  const [draft, setDraft] = useState("");
  const tabs: { id: Tab; label: string }[] = [
    { id: "docket", label: "Docket" },
    { id: "type", label: "Describe" },
    { id: "photo", label: "Photo" },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div role="tablist" aria-label="Ways to bring an exhibit" className="mb-3 grid grid-cols-3 gap-1 rounded border border-brass-800 bg-ink-900/70 p-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            id={`tab-${t.id}`}
            data-testid={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`tabpanel-${t.id}`}
            onClick={() => setTab(t.id)}
            className={`rounded px-2 py-1 text-[0.8rem] font-medium transition-colors ${
              tab === t.id ? "bg-brass-500 text-walnut-950" : "text-parchment-300 hover:text-brass-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div id={`tabpanel-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`} className="scroll-thin min-h-0 flex-1 overflow-y-auto pr-1">
        {tab === "docket" ? (
          <Docket exhibits={exhibits} error={exhibitsError} activeId={activeId} busy={busy} onPick={onPick} />
        ) : tab === "type" ? (
          <TypedExhibit live={live} liveReason={liveReason} busy={busy} text={draft} setText={setDraft} onSubmit={onSubmitTyped} />
        ) : (
          <PhotoExhibit
            live={live}
            liveReason={liveReason}
            busy={busy}
            onDescribe={onDescribePhoto}
            onDescribed={(d) => {
              setDraft(d);
              setTab("type");
            }}
          />
        )}
      </div>
    </div>
  );
}

function Docket({
  exhibits,
  error,
  activeId,
  busy,
  onPick,
}: {
  exhibits: Exhibit[] | null;
  error: string | null;
  activeId: string | null;
  busy: boolean;
  onPick: (ex: Exhibit) => void;
}) {
  if (error) return <p role="alert" className="text-sm text-verdict-red">{error}</p>;
  if (!exhibits) return <p className="text-sm text-parchment-400">Loading the docket…</p>;
  if (exhibits.length === 0) return <p className="text-sm text-parchment-400">The docket is empty.</p>;
  const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  return (
    <ul data-testid="exhibit-picker" className="space-y-2" aria-label="Exhibits on the docket">
      {exhibits.map((ex, i) => {
        const active = ex.exhibit_id === activeId;
        const mystery = ex.mystery;
        return (
          <li key={ex.exhibit_id}>
            <button
              type="button"
              data-testid="exhibit-item"
              data-exhibit-id={ex.exhibit_id}
              data-kind={mystery ? "mystery" : ex.kind}
              onClick={() => onPick(ex)}
              aria-pressed={active}
              aria-label={`Exhibit ${letters[i % 26]}: ${ex.title}${mystery ? ". Mystery exhibit" : ""}`}
              disabled={busy && active}
              className={`group w-full rounded border p-2.5 text-left transition-colors ${
                active
                  ? "border-brass-300 bg-brass-500/15 shadow-glow"
                  : mystery
                    ? "border-dashed border-brass-600 bg-ink-900/60 hover:border-brass-400"
                    : "border-brass-800 bg-ink-900/60 hover:border-brass-500"
              }`}
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-display text-[1.05rem] font-semibold leading-tight text-parchment-50">
                  <span className="mr-1.5 text-brass-400">Ex. {letters[i % 26]}</span>
                  {ex.title}
                </span>
              </div>
              <p className="mt-1 line-clamp-2 text-[0.8rem] leading-snug text-parchment-400">{ex.blurb || ex.description}</p>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {mystery ? <span className="badge border-brass-400 text-brass-300">? Mystery · ruling sealed</span> : null}
                {ex.kind === "timemachine" ? <span className="badge border-verdict-amber/60 text-verdict-amber">Time machine</span> : null}
                {(["single", "multi"] as const)
                  .filter((a) => ex.arms?.[a])
                  .map((a) => (
                    <span key={a} className="badge border-ink-600 text-parchment-300">
                      {a === "multi" ? "Multi-agent" : "Single agent"}
                    </span>
                  ))}
                {ex.objections.length > 0 ? <span className="badge border-verdict-red/50 text-verdict-red">Objection on file</span> : null}
                {ex.placeholder ? <span className="badge border-parchment-500 text-parchment-400">Placeholder</span> : null}
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function ReplayNotice({ what, reason }: { what: string; reason: string }) {
  return (
    <div data-testid="replay-notice" className="mb-3 rounded border border-brass-700 bg-ink-900/70 p-3 text-[0.82rem] leading-snug text-parchment-300">
      <div className="kicker mb-1 text-brass-300">Live mode only</div>
      The court is showing recorded hearings, so {what} is off. Pick an exhibit from the docket to watch a full hearing.
      {reason ? <span className="mt-1 block text-parchment-500">{reason}</span> : null}
    </div>
  );
}

function TypedExhibit({
  live,
  liveReason,
  busy,
  text,
  setText,
  onSubmit,
}: {
  live: boolean;
  liveReason: string;
  busy: boolean;
  text: string;
  setText: (v: string) => void;
  onSubmit: (d: string) => void;
}) {
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (text.trim().length >= 8) onSubmit(text.trim());
  };
  return (
    <form onSubmit={submit}>
      {!live ? <ReplayNotice what="typing a new exhibit" reason={liveReason} /> : null}
      <label htmlFor="typed-exhibit" className="kicker mb-1 block">
        Describe the goods
      </label>
      <textarea
        id="typed-exhibit"
        data-testid="typed-exhibit-input"
        className="field min-h-[7rem] resize-y text-[0.9rem]"
        placeholder="What is it made of, what does it do, how is it built, who uses it?"
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={!live || busy}
        aria-describedby="typed-help"
      />
      <p id="typed-help" className="mt-1 text-xs text-parchment-500">
        Plain facts work best: material, function, form, end use. A live hearing costs a few cents and counts toward this
        session's cap.
      </p>
      <button type="submit" data-testid="typed-exhibit-submit" className="btn-brass mt-2 w-full" disabled={!live || busy || text.trim().length < 8}>
        Submit to the court
      </button>
    </form>
  );
}

function PhotoExhibit({
  live,
  liveReason,
  busy,
  onDescribe,
  onDescribed,
}: {
  live: boolean;
  liveReason: string;
  busy: boolean;
  onDescribe: (image: string) => Promise<string>;
  onDescribed: (d: string) => void;
}) {
  const [image, setImage] = useState<string | null>(null);
  const [camOn, setCamOn] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const stopCam = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setCamOn(false);
  };
  useEffect(() => stopCam, []);

  const startCam = async () => {
    setErr(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      streamRef.current = stream;
      setCamOn(true);
      window.setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          void videoRef.current.play();
        }
      }, 0);
    } catch {
      setErr("The camera is not available. Check browser permissions, or upload a photo instead.");
    }
  };

  const shrink = (src: CanvasImageSource, w: number, h: number) => {
    const canvas = document.createElement("canvas");
    const scale = Math.min(1, 1024 / Math.max(w, h, 1));
    canvas.width = Math.round(w * scale);
    canvas.height = Math.round(h * scale);
    canvas.getContext("2d")?.drawImage(src, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.85);
  };

  const capture = () => {
    const v = videoRef.current;
    if (!v) return;
    setImage(shrink(v, v.videoWidth, v.videoHeight));
    stopCam();
  };

  const onFile = (f: File | undefined) => {
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result !== "string") return;
      const img = new Image();
      img.onload = () => setImage(shrink(img, img.naturalWidth, img.naturalHeight));
      img.src = reader.result;
    };
    reader.readAsDataURL(f);
  };

  const describe = async () => {
    if (!image) return;
    setWorking(true);
    setErr(null);
    try {
      onDescribed(await onDescribe(image));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "The photo could not be described.");
    } finally {
      setWorking(false);
    }
  };

  const disabled = !live || busy || working;
  return (
    <div>
      {!live ? <ReplayNotice what="photo intake" reason={liveReason} /> : null}
      <p className="mb-2 text-[0.8rem] text-parchment-400">
        A vision model writes a description of the photo. You can edit it before the hearing.
      </p>
      <div className="grid grid-cols-2 gap-2">
        <label className={`btn-ghost cursor-pointer ${disabled ? "pointer-events-none opacity-45" : ""}`}>
          <input
            type="file"
            accept="image/*"
            capture="environment"
            className="sr-only"
            disabled={disabled}
            data-testid="photo-input"
            aria-label="Upload a photo of the goods"
            onChange={(e) => onFile(e.target.files?.[0])}
          />
          Upload photo
        </label>
        <button type="button" className="btn-ghost" disabled={disabled} onClick={camOn ? stopCam : startCam} aria-pressed={camOn}>
          {camOn ? "Stop camera" : "Use camera"}
        </button>
      </div>
      {err ? (
        <p role="alert" className="mt-2 text-xs text-verdict-red">
          {err}
        </p>
      ) : null}
      {camOn ? (
        <div className="mt-2 space-y-2">
          <video ref={videoRef} className="w-full rounded border border-brass-700" playsInline muted aria-label="Camera preview" />
          <button type="button" className="btn-brass w-full" onClick={capture}>
            Capture
          </button>
        </div>
      ) : null}
      {image ? (
        <div className="mt-2">
          <img src={image} alt="Exhibit photo to describe" className="max-h-40 w-full rounded border border-brass-700 object-contain" />
          <button type="button" className="mt-1 text-xs text-parchment-400 underline" onClick={() => setImage(null)}>
            Remove photo
          </button>
        </div>
      ) : (
        <div className="mt-2 flex h-24 items-center justify-center rounded border border-dashed border-brass-800 text-xs text-parchment-500">
          No photo yet
        </div>
      )}
      <button type="button" data-testid="photo-describe" className="btn-brass mt-2 w-full" disabled={disabled || !image} onClick={describe}>
        {working ? "Describing…" : "Describe the photo"}
      </button>
    </div>
  );
}

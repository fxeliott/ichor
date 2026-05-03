/**
 * AudioPlayer — minimal HTML5 audio player for briefing TTS playback.
 *
 * Phase 0: thin wrapper around <audio>. Phase 2+ : custom controls + speed
 * + playlist + waveform.
 */

import * as React from "react";

export interface AudioPlayerProps {
  src: string;
  /** Optional title shown above (e.g. "Briefing pre-Londres 06:00 Paris"). */
  label?: string;
  autoPlay?: boolean;
  /** URL/anchor to the equivalent transcript (typically the briefing
   *  markdown body). Required to satisfy WCAG 2.1.1 / 1.2.2 for prerecorded
   *  audio-only content. */
  transcriptHref?: string;
}

export const AudioPlayer: React.FC<AudioPlayerProps> = ({
  src,
  label,
  autoPlay = false,
  transcriptHref,
}) => {
  return (
    <div className="flex flex-col gap-2 p-3 bg-neutral-900/40 border border-neutral-800 rounded-md">
      {label && (
        <span className="text-xs text-neutral-400 font-medium">{label}</span>
      )}
      <audio
        controls
        src={src}
        autoPlay={autoPlay}
        preload="metadata"
        className="w-full"
        aria-label={label ?? "Briefing audio"}
      >
        Votre navigateur ne supporte pas l'élément audio HTML5.
      </audio>
      {transcriptHref && (
        <a
          href={transcriptHref}
          className="text-xs text-emerald-400 hover:text-emerald-300 underline-offset-2 hover:underline"
        >
          Lire la transcription écrite (équivalent texte)
        </a>
      )}
    </div>
  );
};

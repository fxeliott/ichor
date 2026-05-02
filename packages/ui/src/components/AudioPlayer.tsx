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
}

export const AudioPlayer: React.FC<AudioPlayerProps> = ({
  src,
  label,
  autoPlay = false,
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
    </div>
  );
};

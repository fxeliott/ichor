/**
 * AmbientOrbs — animated floating gradient blobs for hero / page bg.
 *
 * Pure CSS animation (respects prefers-reduced-motion via globals.css).
 * Place at top of a relatively-positioned container with overflow-hidden.
 */

export function AmbientOrbs({
  variant = "default",
}: {
  variant?: "default" | "long" | "short" | "alert";
}) {
  const palette: Record<typeof variant, [string, string]> = {
    default: ["rgba(59, 130, 246, 0.35)", "rgba(96, 165, 250, 0.20)"],
    long: ["rgba(16, 185, 129, 0.30)", "rgba(52, 211, 153, 0.18)"],
    short: ["rgba(244, 63, 94, 0.30)", "rgba(248, 113, 113, 0.18)"],
    alert: ["rgba(245, 158, 11, 0.30)", "rgba(251, 191, 36, 0.18)"],
  };
  const [c1, c2] = palette[variant];
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 overflow-hidden"
    >
      <div
        className="ichor-orb"
        style={{
          width: 400,
          height: 400,
          top: "-100px",
          left: "10%",
          background: c1,
          animationDelay: "0s",
        }}
      />
      <div
        className="ichor-orb"
        style={{
          width: 320,
          height: 320,
          top: "20%",
          right: "5%",
          background: c2,
          animationDelay: "-6s",
        }}
      />
      <div
        className="ichor-orb"
        style={{
          width: 260,
          height: 260,
          bottom: "-60px",
          left: "50%",
          background: c1,
          animationDelay: "-12s",
          opacity: 0.3,
        }}
      />
    </div>
  );
}

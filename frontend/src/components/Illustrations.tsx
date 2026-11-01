import React from "react";

interface IllustrationProps {
  size?: number;
  className?: string;
  color?: string;
  tealColor?: string;
}

/**
 * Monoline Architectural Lighthouse — System Health Beacon
 */
export const LighthouseIllustration: React.FC<IllustrationProps> = ({
  size = 180,
  className = "",
  color = "currentColor",
  tealColor = "var(--teal)",
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 100 100"
    fill="none"
    stroke={color}
    strokeWidth="1.2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    {/* Base rocks / masonry */}
    <path d="M22 88 C32 85 45 87 55 86 C65 85 75 88 82 87" />
    <path d="M18 92 C30 90 48 91 62 90 C72 89 80 92 86 91" />
    <path d="M26 88 L34 38 L66 38 L74 88" />
    <path d="M30 64 L70 64" />
    <path d="M32 50 L68 50" />
    <path d="M35 76 L65 76" />

    {/* Slender windows */}
    <line x1="50" y1="56" x2="50" y2="60" />
    <line x1="50" y1="69" x2="50" y2="73" />

    {/* Gallery and Lantern Room */}
    <path d="M30 38 L70 38" />
    <path d="M32 38 L32 24 L68 24 L68 38" />
    <line x1="41" y1="24" x2="41" y2="38" />
    <line x1="50" y1="24" x2="50" y2="38" />
    <line x1="59" y1="24" x2="59" y2="38" />

    {/* Dome and Spire */}
    <path d="M32 24 C32 14 68 14 68 24" />
    <line x1="50" y1="14" x2="50" y2="8" />
    <circle cx="50" cy="7" r="1.5" />

    {/* The Solitary Electric Teal Focal Ray */}
    <line x1="50" y1="31" x2="88" y2="18" stroke={tealColor} strokeWidth="1.2" strokeDasharray="2 3" />
    <circle cx="50" cy="31" r="2.2" stroke={tealColor} fill="none" />
  </svg>
);

/**
 * Monoline Rackmount Router / Gateway
 */
export const RouterIllustration: React.FC<IllustrationProps> = ({
  size = 140,
  className = "",
  color = "currentColor",
  tealColor = "var(--teal)",
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 100 100"
    fill="none"
    stroke={color}
    strokeWidth="1.2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    {/* Chassis */}
    <rect x="15" y="38" width="70" height="24" rx="1" />
    <line x1="15" y1="43" x2="85" y2="43" />
    
    {/* Rack ears */}
    <path d="M12 36 L15 38 L15 62 L12 64 Z" />
    <circle cx="13.5" cy="42" r="0.8" />
    <circle cx="13.5" cy="58" r="0.8" />
    <path d="M88 36 L85 38 L85 62 L88 64 Z" />
    <circle cx="86.5" cy="42" r="0.8" />
    <circle cx="86.5" cy="58" r="0.8" />

    {/* RJ45 Port Arrays */}
    <rect x="22" y="48" width="6" height="8" />
    <rect x="31" y="48" width="6" height="8" />
    <rect x="40" y="48" width="6" height="8" />
    <rect x="49" y="48" width="6" height="8" />

    {/* Vent Grille */}
    <line x1="60" y1="49" x2="68" y2="49" />
    <line x1="60" y1="52" x2="68" y2="52" />
    <line x1="60" y1="55" x2="68" y2="55" />

    {/* Single Electric Teal Status Beacon */}
    <circle cx="78" cy="52" r="1.8" stroke={tealColor} strokeWidth="1.2" />
  </svg>
);

/**
 * Monoline Wireless Antenna & Wave Arcs
 */
export const AntennaIllustration: React.FC<IllustrationProps> = ({
  size = 140,
  className = "",
  color = "currentColor",
  tealColor = "var(--teal)",
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 100 100"
    fill="none"
    stroke={color}
    strokeWidth="1.2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    {/* Base Mast & Guy Wires */}
    <line x1="50" y1="36" x2="50" y2="82" />
    <line x1="32" y1="82" x2="50" y2="58" />
    <line x1="68" y1="82" x2="50" y2="58" />
    <line x1="28" y1="82" x2="72" y2="82" />

    {/* Mast Head */}
    <circle cx="50" cy="34" r="3" />
    
    {/* Propagation Wave Arcs */}
    <path d="M40 24 C45 19 55 19 60 24" />
    <path d="M32 16 C42 8 58 8 68 16" />
    {/* Single Active Teal Wave */}
    <path d="M24 8 C38 -2 62 -2 76 8" stroke={tealColor} strokeWidth="1.2" />
  </svg>
);

/**
 * Monoline Tangled Physical Cable & Jack
 */
export const CableIllustration: React.FC<IllustrationProps> = ({
  size = 140,
  className = "",
  color = "currentColor",
  tealColor = "var(--teal)",
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 100 100"
    fill="none"
    stroke={color}
    strokeWidth="1.2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    {/* Intertwined cable curves */}
    <path d="M16 75 C32 82 44 48 56 68 C64 80 82 72 78 52 C74 34 50 38 42 22" />
    <path d="M20 62 C34 68 40 40 52 50 C62 58 72 45 68 35" strokeDasharray="3 3" opacity="0.6" />

    {/* Terminal Jack */}
    <rect x="36" y="14" width="12" height="16" rx="1" />
    <line x1="42" y1="14" x2="42" y2="8" />
    <circle cx="42" cy="7" r="1.5" stroke={tealColor} />
  </svg>
);

/**
 * Monoline Cartographic Compass Rose
 */
export const CompassIllustration: React.FC<IllustrationProps> = ({
  size = 140,
  className = "",
  color = "currentColor",
  tealColor = "var(--teal)",
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 100 100"
    fill="none"
    stroke={color}
    strokeWidth="1.2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <circle cx="50" cy="50" r="34" />
    <circle cx="50" cy="50" r="30" strokeDasharray="1 3" />
    
    {/* Axes */}
    <line x1="50" y1="12" x2="50" y2="88" />
    <line x1="12" y1="50" x2="88" y2="50" />

    {/* Compass Pointer */}
    <polygon points="50,20 54,46 50,42 46,46" stroke={tealColor} />
    <polygon points="50,80 54,54 50,58 46,54" />
    <circle cx="50" cy="50" r="2.5" />
  </svg>
);

/**
 * Monoline Investigative Lens
 */
export const MagnifierIllustration: React.FC<IllustrationProps> = ({
  size = 140,
  className = "",
  color = "currentColor",
  tealColor = "var(--teal)",
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 100 100"
    fill="none"
    stroke={color}
    strokeWidth="1.2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <circle cx="42" cy="42" r="24" />
    <circle cx="42" cy="42" r="20" strokeDasharray="2 3" opacity="0.5" />
    <line x1="59" y1="59" x2="82" y2="82" strokeWidth="2.2" />
    
    {/* Fine focal tick inside glass */}
    <line x1="38" y1="42" x2="46" y2="42" stroke={tealColor} />
    <line x1="42" y1="38" x2="42" y2="46" stroke={tealColor} />
  </svg>
);

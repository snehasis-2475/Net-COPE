/** Hex values mirrored from the CSS tokens in index.css, for WebGL materials. */
export const INK = "#121212";
export const PAPER = "#DAD9D4";
export const SIGNAL = "#F5C21B";

/** Thin-film style gradient (violet → magenta → coral → electric blue), looped. */
export const IRIDESCENT_GLSL = /* glsl */ `
vec3 iridescent(float t) {
  t = fract(t);
  vec3 violet = vec3(0.32, 0.10, 0.86);
  vec3 magenta = vec3(0.96, 0.16, 0.66);
  vec3 coral = vec3(1.00, 0.45, 0.50);
  vec3 blue = vec3(0.12, 0.44, 1.00);
  if (t < 0.25) return mix(violet, magenta, t / 0.25);
  if (t < 0.5) return mix(magenta, coral, (t - 0.25) / 0.25);
  if (t < 0.75) return mix(coral, blue, (t - 0.5) / 0.25);
  return mix(blue, violet, (t - 0.75) / 0.25);
}
`;

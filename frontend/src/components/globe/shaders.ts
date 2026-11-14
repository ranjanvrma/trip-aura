// GLSL for the globe. Photo textures are sRGB and are decoded to linear light by three; each fragment shader ends
// with three's colorspace chunk, so what reaches the screen matches the imagery.

/** Used by the halo: object position plus view-space normal and position. */
export const surfaceVertex = /* glsl */ `
varying vec3 vObj;
varying vec3 vNormalV;
varying vec3 vPosV;
void main() {
  vObj = position;
  vNormalV = normalize(normalMatrix * normal);
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  vPosV = mv.xyz;
  gl_Position = projectionMatrix * mv;
}
`;

/**
 * The Earth's surface. three's sphere starts its u coordinate at longitude -90 (see geo.ts), and the imagery starts
 * at -180, hence the quarter-turn offset. The sun direction is also carried into view space for the ocean glint.
 */
export const earthVertex = /* glsl */ `
uniform vec3 uSun;
varying vec2 vUv;
varying vec3 vObj;
varying vec3 vNormalV;
varying vec3 vPosV;
varying vec3 vSunV;
void main() {
  vUv = vec2(uv.x + 0.25, uv.y);
  vObj = position;
  vNormalV = normalize(normalMatrix * normal);
  vSunV = normalize(normalMatrix * uSun);
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  vPosV = mv.xyz;
  gl_Position = projectionMatrix * mv;
}
`;

export const earthFragment = /* glsl */ `
uniform sampler2D uDay;
uniform sampler2D uNight;
uniform sampler2D uWater;
uniform sampler2D uClouds;
uniform vec3 uSun;
uniform vec3 uAtmosphere;
varying vec2 vUv;
varying vec3 vObj;
varying vec3 vNormalV;
varying vec3 vPosV;
varying vec3 vSunV;

void main() {
  vec3 p = normalize(vObj);
  vec3 n = normalize(vNormalV);
  vec3 v = normalize(-vPosV);
  float rim = 1.0 - clamp(dot(n, v), 0.0, 1.0);

  // How high the sun is here: 1 under the sun, 0 at the terminator, negative at night.
  float sunDot = dot(p, uSun);
  float day = smoothstep(-0.1, 0.22, sunDot);      // the twilight band, about 18 degrees wide
  float direct = clamp(sunDot, 0.0, 1.0);

  vec3 ground = texture2D(uDay, vUv).rgb;
  float water = texture2D(uWater, vUv).r;
  float cloud = texture2D(uClouds, vUv).r;

  // Day side: the satellite picture under sunlight, the sun glinting off water, clouds on top.
  vec3 lit = ground * (0.3 + 1.0 * direct);
  vec3 halfway = normalize(normalize(vSunV) + v);
  lit += vec3(1.0, 0.95, 0.84) * pow(max(dot(n, halfway), 0.0), 220.0) * water * 0.38;
  lit = mix(lit, vec3(0.34 + 0.72 * direct), cloud * 0.7);

  // Night side: city lights on a dark surface; clouds hide some of them.
  vec3 night = texture2D(uNight, vUv).rgb * 0.95;
  night = mix(night, vec3(0.03, 0.04, 0.06), cloud * 0.55);

  vec3 col = mix(night, lit, day);

  // Air: a thin blue veil that thickens toward the limb, brightest on the day side, with a warm line at dusk.
  float air = pow(rim, 2.4);
  col = mix(col, uAtmosphere, air * (0.18 + 0.6 * day));
  float dusk = smoothstep(-0.12, 0.02, sunDot) * (1.0 - smoothstep(0.02, 0.3, sunDot));
  col += vec3(0.9, 0.42, 0.2) * dusk * air * 0.12;

  gl_FragColor = vec4(col, 1.0);
  #include <colorspace_fragment>
}
`;

/** Rendered on the back faces of a slightly larger sphere: strongest at the globe's edge, gone at its own. */
export const haloFragment = /* glsl */ `
uniform vec3 uColor;
uniform float uStrength;
varying vec3 vObj;
varying vec3 vNormalV;
varying vec3 vPosV;
void main() {
  float t = dot(normalize(vNormalV), normalize(vPosV));
  float a = pow(smoothstep(0.0, 0.5, t), 1.8) * uStrength;
  gl_FragColor = vec4(uColor, a);
  #include <colorspace_fragment>
}
`;
